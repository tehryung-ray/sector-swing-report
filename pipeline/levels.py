# -*- coding: utf-8 -*-
"""지지/저항 기반 가격대 산출 (기획서 3단계).

## 왜 국면을 나누는가
추세 추종과 눌림목 진입은 구조적으로 상충한다. 추세가 강할수록 지지선에서 멀어지므로
"강한 추세" + "지지선 근처"를 동시에 요구하면 실제로는 추세가 식은 종목만 통과한다.
그래서 20일선 이격도로 국면을 나누고, **얼마나 깊은 눌림을 기다릴지**를 다르게 잡는다.

## 실행 제약: 모든 진입가는 예약 지정가 매수로 걸 수 있어야 한다
사용자는 아침 7시에 리포트를 보고 장 시작 전에 주문을 예약한다(한국투자증권).
예약주문은 조건부가 아니다. "X원을 돌파하면 매수" 같은 조건을 걸 수 없다.
현재가보다 **위**에 지정가 매수를 걸면 조건 충족이 아니라 개장 즉시 시가에 체결되는데,
이는 기획서가 경계한 갭상승 추격 그 자체다.

따라서 진입가는 **항상 전일 종가 이하**로만 산출한다.
직전 10일 고가(돌파선)는 참고 정보로만 제공하고 진입가로 쓰지 않는다.

## 갭 대응
지정가 매수는 갭상승하면 그냥 미체결된다(= 추격 금지 원칙이 자동으로 지켜진다).
실제 위험은 갭하락이다. 시가가 손절가 아래로 열리면 셋업은 이미 무효이므로 주문을 취소한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .util import pct, round_tick

# --- 국면 구분 (20일선 이격도) ---
PULLBACK_MAX = 0.04   # 이 이하면 깊은 눌림(20일선)까지 기다린다
EXTENDED_MAX = 0.12   # 이 초과면 과열, 관망

# --- 눌림목형 손절 (기획서: -2% ~ -3%) ---
PB_MIN_LOSS, PB_MAX_LOSS = 0.025, 0.030
# --- 얕은눌림형 손절 (추세 진행 중이라 변동성이 커서 조금 넓게) ---
SH_MIN_LOSS, SH_MAX_LOSS = 0.020, 0.035

DIP_ATR = 0.5         # 얕은눌림형이 기다리는 폭 = 0.5 x ATR
MIN_TP1 = 0.025       # 저항이 이미 뚫린 경우의 최소 1차 목표

# 얕은눌림형 목표 배수. TP1_ATR 은 워크포워드 최적화로 1.5 -> 2.0 상향했다.
# 훈련구간(2015~2020) 상위 30개 조합에서 30/30 으로 선택된, 가장 안정적인 파라미터다.
# 1.5 는 추세가 살아있는 종목을 너무 일찍 청산시켜 이익을 잘라먹었다.
TP1_ATR, TP1_RISK = 2.0, 1.3
TP2_ATR, TP2_RISK = 3.0, 2.5

PULLBACK, SHALLOW, EXTENDED, DOWNTREND = "pullback", "shallow", "extended", "downtrend"
SETUP_LABEL = {
    PULLBACK: "깊은눌림형",
    SHALLOW: "얕은눌림형",
    EXTENDED: "과열",
    DOWNTREND: "하락추세",
}
SETUP_HOWTO = {
    PULLBACK: "20일선까지 내려오면 매수. 진입가에 지정가 예약을 걸고 기다립니다. 안 내려오면 안 사면 됩니다.",
    SHALLOW: "추세가 진행 중이라 20일선은 멉니다. 장중 얕은 눌림에 지정가 예약을 걸어 담습니다.",
    EXTENDED: "20일선에서 너무 멀어졌습니다. 조정을 기다립니다.",
    DOWNTREND: "20일선 아래입니다. 추세가 돌아설 때까지 봅니다.",
}
ORDER_NOTE = "지정가 매수 (장 시작 전 예약주문 가능)"


def _atr(df: pd.DataFrame, n: int = 14) -> float:
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return float(tr.rolling(n).mean().iloc[-1])


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_levels(df: pd.DataFrame) -> dict | None:
    """일봉 OHLCV -> 국면 판정 + 진입/1차·2차 익절/손절."""
    if df is None or len(df) < 60:
        return None

    close, high, low, vol = df["Close"], df["High"], df["Low"], df["Volume"]
    last = float(close.iloc[-1])

    ma20_s = close.rolling(20).mean()
    ma20, ma60 = float(ma20_s.iloc[-1]), float(close.rolling(60).mean().iloc[-1])
    sd20 = float(close.rolling(20).std().iloc[-1])
    low5 = float(low.rolling(5).min().iloc[-1])
    swing_low = float(low.rolling(20).min().iloc[-1])
    hi10 = float(high.rolling(10).max().iloc[-1])
    hi60 = float(high.rolling(60).max().iloc[-1])
    atr = _atr(df)
    bb_up = ma20 + 2.0 * sd20

    vals = (last, ma20, ma60, sd20, low5, swing_low, hi10, hi60, atr)
    if not all(np.isfinite(x) for x in vals) or atr <= 0:
        return None

    above_ma20 = last > ma20
    ma_stacked = ma20 > ma60
    ma20_rising = bool(np.isfinite(ma20_s.iloc[-6]) and ma20 > float(ma20_s.iloc[-6]))
    ext = (last - ma20) / ma20

    if not above_ma20:
        setup = DOWNTREND
    elif ext > EXTENDED_MAX:
        setup = EXTENDED
    elif ext <= PULLBACK_MAX:
        setup = PULLBACK
    else:
        setup = SHALLOW

    if setup == PULLBACK:
        # 20일선까지 깊게 기다린다. 머리 위에 실제 저항이 있으므로 그 저항을 목표로 쓴다.
        entry_raw = max(ma20, low5)
        tp1_raw = max(hi10, entry_raw * (1 + MIN_TP1))
        tp2_raw = min(bb_up, hi60)
        if tp2_raw <= tp1_raw:
            # 2차는 1차보다 위여야 한다. 다만 max() 로 고르면 가장 먼 값을 집어버린다.
            # 60일 고가는 크게 하락한 종목에서 현재가보다 한참 위에 있을 수 있다
            # (예: TIGER 200 IT 2026-09-08, 60일 고가가 현재가 대비 +54%).
            # 1차를 넘는 후보 중 가장 가까운 값을 쓴다.
            tp2_raw = min(x for x in (bb_up, hi60, tp1_raw * 1.04) if x > tp1_raw)
        stop_raw = _clamp(
            min(swing_low * 0.99, entry_raw * (1 - PB_MIN_LOSS)),
            entry_raw * (1 - PB_MAX_LOSS), entry_raw * (1 - PB_MIN_LOSS),
        )
        basis = "저항선"
    else:
        # 20일선이 멀다. 0.5 ATR 정도의 얕은 눌림에 건다 (체결 가능성 확보).
        entry_raw = max(low5, last - DIP_ATR * atr)
        stop_raw = _clamp(
            entry_raw - atr,
            entry_raw * (1 - SH_MAX_LOSS), entry_raw * (1 - SH_MIN_LOSS),
        )
        risk_raw = entry_raw - stop_raw
        # 신고가 부근이라 머리 위 저항이 없다 -> ATR 측정이동으로 투영
        tp1_raw = entry_raw + max(TP1_ATR * atr, TP1_RISK * risk_raw)
        tp2_raw = entry_raw + max(TP2_ATR * atr, TP2_RISK * risk_raw)
        basis = "ATR 투영"

    # 예약 지정가 매수 제약: 진입가는 반드시 전일 종가 이하
    entry_raw = min(entry_raw, last)

    entry = round_tick(entry_raw, "down")   # 조금 낮게 사는 쪽이 보수적
    tp1 = round_tick(tp1_raw, "down")       # 조금 일찍 파는 쪽이 보수적
    tp2 = round_tick(tp2_raw, "down")
    stop = round_tick(stop_raw, "up")       # 조금 일찍 자르는 쪽이 보수적

    risk, reward = entry - stop, tp1 - entry
    rr = round(reward / risk, 2) if risk > 0 else 0.0
    turnover = float((close * vol).rolling(20).mean().iloc[-1])

    return {
        "setup": setup,
        "setup_label": SETUP_LABEL[setup],
        "setup_howto": SETUP_HOWTO[setup],
        "order_note": ORDER_NOTE,
        "target_basis": basis,
        "last_close": round_tick(last),
        "entry": entry, "tp1": tp1, "tp2": tp2, "stop": stop,
        "tp1_pct": pct(tp1, entry),
        "tp2_pct": pct(tp2, entry),
        "stop_pct": pct(stop, entry),
        "rr": rr,
        "cancel_below": stop,                    # 시가가 이 아래면 예약주문 취소
        "breakout_ref": round_tick(hi10),        # 참고: 이 위로 뚫으면 추세 강화
        "entry_vs_last_pct": pct(entry, last),   # 항상 0 이하 (지정가 매수 제약)
        "ext_pct": round(ext * 100, 2),
        "atr_pct": round(atr / last * 100, 2),
        "ma20": round_tick(ma20), "ma60": round_tick(ma60),
        "swing_low": round_tick(swing_low),
        "kr_above_ma20": bool(above_ma20),
        "kr_ma_stacked": bool(ma_stacked),
        "kr_ma20_rising": ma20_rising,
        "turnover_eok": round(turnover / 1e8, 1),
    }

# -*- coding: utf-8 -*-
"""지지/저항 기반 가격대 산출 (기획서 3단계).

핵심 설계: 진입 방식을 하나로 두면 모순이 생긴다.
  추세가 강할수록 지지선에서 멀어지므로, '추세 추종'과 '지지선 눌림목 진입'은
  동시에 만족될 수 없다. 지지선에 가깝다는 건 오히려 추세가 식고 있다는 뜻이다.

그래서 20일선 이격도로 국면을 나누고 진입 방식 자체를 바꾼다.
  - 이격도 <= 4%   : 눌림목형(PULLBACK) - 지지선에 지정가를 걸고 기다린다.
  - 4% < 이격 <=12%: 돌파형(BREAKOUT)   - 눌림을 기다리면 못 산다. 직전 고가 돌파에 진입.
  - 이격도 > 12%   : 과열(EXTENDED)     - 어느 쪽도 아니다. 관망.

목표가 산출 근거도 국면에 따라 다르다.
  - 눌림목형: 머리 위에 실제 저항(10일/60일 고가)이 있으므로 그 저항을 목표로 쓴다.
  - 돌파형  : 신고가 부근이라 머리 위 저항이 없다. ATR 기반 측정이동으로 투영한다.
    (이 값은 '관측된 저항'이 아니라 '변동성 투영'이므로 target_basis 로 구분해 표기한다.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .util import pct, round_tick

# --- 국면 구분 (20일선 이격도) ---
PULLBACK_MAX = 0.04   # 이 이하면 눌림목형
EXTENDED_MAX = 0.12   # 이 초과면 과열, 관망

# --- 눌림목형 손절 (기획서: -2% ~ -3%) ---
PB_MIN_LOSS, PB_MAX_LOSS = 0.025, 0.030
# --- 돌파형 손절 (변동성이 커서 조금 넓게) ---
BO_MIN_LOSS, BO_MAX_LOSS = 0.020, 0.035

MIN_TP1 = 0.025       # 저항이 이미 뚫린 경우의 최소 1차 목표
GAP_GUARD = 0.015     # 시가가 진입가 +1.5% 위면 보류

PULLBACK, BREAKOUT, EXTENDED, DOWNTREND = "pullback", "breakout", "extended", "downtrend"
SETUP_LABEL = {
    PULLBACK: "눌림목형",
    BREAKOUT: "돌파형",
    EXTENDED: "과열",
    DOWNTREND: "하락추세",
}
SETUP_HOWTO = {
    PULLBACK: "진입가에 지정가 매수를 걸고 기다립니다. 안 내려오면 안 사면 됩니다.",
    BREAKOUT: "진입가를 위로 돌파할 때 진입합니다. 돌파 못 하면 진입하지 않습니다.",
}


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

    # --- 추세 판정 ---
    above_ma20 = last > ma20
    ma_stacked = ma20 > ma60
    ma20_rising = bool(np.isfinite(ma20_s.iloc[-6]) and ma20 > float(ma20_s.iloc[-6]))
    ext = (last - ma20) / ma20   # 20일선 이격도

    # --- 국면 결정 ---
    if not above_ma20:
        setup = DOWNTREND
    elif ext > EXTENDED_MAX:
        setup = EXTENDED
    elif ext <= PULLBACK_MAX:
        setup = PULLBACK
    else:
        setup = BREAKOUT

    if setup == PULLBACK:
        # 지지선에 지정가 대기. 진입가는 현재가 이하여야 성립한다.
        entry_raw = min(max(ma20, low5), last)
        tp1_raw = max(hi10, entry_raw * (1 + MIN_TP1))
        tp2_raw = min(bb_up, hi60)
        if tp2_raw <= tp1_raw:
            tp2_raw = max(bb_up, hi60, tp1_raw * 1.04)
        stop_raw = _clamp(
            min(swing_low * 0.99, entry_raw * (1 - PB_MIN_LOSS)),
            entry_raw * (1 - PB_MAX_LOSS), entry_raw * (1 - PB_MIN_LOSS),
        )
        basis = "저항선"
    else:
        # 돌파형/과열/하락추세 모두 돌파 기준으로 계산해 두고, 채택 여부는 gates 가 판단한다.
        entry_raw = max(hi10, last)  # 직전 10일 고가 = 돌파 확인선
        stop_raw = _clamp(
            entry_raw - atr,
            entry_raw * (1 - BO_MAX_LOSS), entry_raw * (1 - BO_MIN_LOSS),
        )
        risk_raw = entry_raw - stop_raw
        # 신고가 부근이라 머리 위 저항이 없다 -> ATR 측정이동으로 투영
        tp1_raw = entry_raw + max(1.5 * atr, 1.3 * risk_raw)
        tp2_raw = entry_raw + max(3.0 * atr, 2.5 * risk_raw)
        basis = "ATR 투영"

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
        "setup_howto": SETUP_HOWTO.get(setup, "진입 조건을 만족하지 않습니다."),
        "target_basis": basis,
        "last_close": round_tick(last),
        "entry": entry, "tp1": tp1, "tp2": tp2, "stop": stop,
        "tp1_pct": pct(tp1, entry),
        "tp2_pct": pct(tp2, entry),
        "stop_pct": pct(stop, entry),
        "rr": rr,
        "gap_guard": round_tick(entry * (1 + GAP_GUARD), "up"),
        "entry_vs_last_pct": pct(entry, last),  # 음수=눌림목 대기, 양수=돌파 대기
        "ext_pct": round(ext * 100, 2),         # 20일선 이격도
        "atr_pct": round(atr / last * 100, 2),
        "ma20": round_tick(ma20), "ma60": round_tick(ma60),
        "swing_low": round_tick(swing_low),
        "kr_above_ma20": bool(above_ma20),
        "kr_ma_stacked": bool(ma_stacked),
        "kr_ma20_rising": ma20_rising,
        "turnover_eok": round(turnover / 1e8, 1),
    }

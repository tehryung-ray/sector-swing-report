# -*- coding: utf-8 -*-
"""지지/저항 기반 가격대 산출 (기획서 3단계).

설계 원칙
- 이 전략은 '추세 추종 + 눌림목 진입'이다. 따라서 국내 종목 자체가 상승 추세일 때만
  진입가를 계산한다. 하락 추세 종목은 gates 에서 걸러진다.
- 진입가는 '가장 가까운 유효 지지'다. 20일선과 최근 5일 저가 중 높은 쪽을 쓴다.
  20일선만 쓰면 강한 상승 종목의 진입가가 지나치게 멀어져 영원히 체결되지 않는다.
- 손절은 기획서대로 -2%~-3% 구간에 강제한다. 스윙 저점에 딱 붙이면
  일중 변동에 즉시 털리고(휩쏘), 손익비도 비현실적으로 부풀려진다.
- 모든 가격은 호가단위(ETF 5원)에 정렬한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .util import pct, round_tick

MAX_LOSS = 0.030   # 손절 상한 -3%
MIN_LOSS = 0.025   # 손절 하한 -2.5%
MIN_TP1 = 0.025    # 저항이 이미 뚫린 경우의 최소 1차 목표 +2.5%
GAP_GUARD = 0.015  # 시가가 진입가 +1.5% 위면 보류


def compute_levels(df: pd.DataFrame) -> dict | None:
    """일봉 OHLCV -> 진입/1차익절/2차익절/손절 및 부가 지표."""
    if df is None or len(df) < 60:
        return None

    close, high, low, vol = df["Close"], df["High"], df["Low"], df["Volume"]
    last = float(close.iloc[-1])

    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma60 = float(close.rolling(60).mean().iloc[-1])
    sd20 = float(close.rolling(20).std().iloc[-1])
    low5 = float(low.rolling(5).min().iloc[-1])       # 가장 가까운 단기 지지
    swing_low = float(low.rolling(20).min().iloc[-1])  # 추세 무효화 지점
    hi10 = float(high.rolling(10).max().iloc[-1])      # 단기 저항
    hi60 = float(high.rolling(60).max().iloc[-1])      # 중기 저항
    bb_up = ma20 + 2.0 * sd20

    vals = (last, ma20, ma60, sd20, low5, swing_low, hi10, hi60)
    if not all(np.isfinite(x) for x in vals):
        return None

    # --- 국내 추세 판정 (gates 에서 사용) ---
    above_ma20 = last > ma20
    ma_stacked = ma20 > ma60

    # --- 진입가: 20일선과 최근 5일 저가 중 높은 쪽 = 가장 가까운 유효 지지 ---
    entry_raw = max(ma20, low5)
    entry_raw = min(entry_raw, last)  # 현재가보다 높은 진입가는 성립하지 않는다

    # --- 1차 익절: 최근 10일 고가. 이미 뚫려 있으면 최소 목표를 준다 ---
    tp1_raw = max(hi10, entry_raw * (1 + MIN_TP1))

    # --- 2차 익절: 볼린저 상단과 60일 고가 중 낮은 쪽 (과도한 목표 방지) ---
    tp2_raw = min(bb_up, hi60)
    if tp2_raw <= tp1_raw:
        tp2_raw = max(bb_up, hi60, tp1_raw * 1.04)

    # --- 손절: -2.5% ~ -3% 구간에 강제. 스윙 저점이 더 가까우면 그쪽을 쓴다 ---
    stop_raw = min(swing_low * 0.99, entry_raw * (1 - MIN_LOSS))
    stop_raw = max(stop_raw, entry_raw * (1 - MAX_LOSS))

    entry = round_tick(entry_raw, "down")   # 조금 낮게 사는 쪽이 보수적
    tp1 = round_tick(tp1_raw, "down")       # 조금 일찍 파는 쪽이 보수적
    tp2 = round_tick(tp2_raw, "down")
    stop = round_tick(stop_raw, "up")       # 조금 일찍 자르는 쪽이 보수적

    risk, reward = entry - stop, tp1 - entry
    rr = round(reward / risk, 2) if risk > 0 else 0.0

    turnover = float((close * vol).rolling(20).mean().iloc[-1])

    return {
        "last_close": round_tick(last),
        "entry": entry, "tp1": tp1, "tp2": tp2, "stop": stop,
        "tp1_pct": pct(tp1, entry),
        "tp2_pct": pct(tp2, entry),
        "stop_pct": pct(stop, entry),
        "rr": rr,
        "gap_guard": round_tick(entry * (1 + GAP_GUARD), "up"),
        "dist_from_entry_pct": pct(last, entry),  # 진입가까지 기다려야 할 폭
        "ma20": round_tick(ma20),
        "ma60": round_tick(ma60),
        "swing_low": round_tick(swing_low),
        "kr_above_ma20": bool(above_ma20),
        "kr_ma_stacked": bool(ma_stacked),
        "turnover_eok": round(turnover / 1e8, 1),
    }

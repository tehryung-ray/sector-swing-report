# -*- coding: utf-8 -*-
"""미국 섹터 모멘텀 랭킹 및 시장 국면 판정 (기획서 1단계)."""
from __future__ import annotations

import numpy as np
import pandas as pd

# 신호 등급
STRONG, TURNING, NEUTRAL, WEAK = "strong", "turning", "neutral", "weak"
LABEL = {
    STRONG: "강한 상승",
    TURNING: "상승 전환",
    NEUTRAL: "중립",
    WEAK: "하락세",
}


def _ret(close: pd.Series, n: int) -> float:
    if len(close) <= n:
        return 0.0
    return float(close.iloc[-1] / close.iloc[-1 - n] - 1.0)


def market_regime(spy: pd.DataFrame, ma_len: int = 200) -> dict:
    """SPY 200일선 기준 위험선호/위험회피 판정."""
    c = spy["Close"]
    ma = c.rolling(ma_len).mean().iloc[-1]
    last = float(c.iloc[-1])
    above = bool(np.isfinite(ma) and last > ma)
    return {
        "spy_close": round(last, 2),
        "spy_ma200": round(float(ma), 2) if np.isfinite(ma) else None,
        "risk_on": above,
        "label": "위험선호" if above else "위험회피",
        "note": (
            "S&P500이 200일선 위입니다. 정상적으로 스윙 진입을 검토할 수 있는 국면입니다."
            if above else
            "S&P500이 200일선 아래입니다. 약세 국면이므로 비중을 줄이고 손절을 더 엄격히 지키세요."
        ),
    }


def rank_sectors(us: dict[str, pd.DataFrame], sectors: list[dict], benchmark: str) -> list[dict]:
    """섹터별 모멘텀 점수 산출 후 랭킹."""
    bench = us.get(benchmark)
    bench_r20 = _ret(bench["Close"], 20) if bench is not None else 0.0

    rows = []
    for s in sectors:
        t = s["ticker"]
        df = us.get(t)
        if df is None or len(df) < 60:
            continue
        c = df["Close"]
        r1, r5, r20 = _ret(c, 1), _ret(c, 5), _ret(c, 20)
        ma20 = c.rolling(20).mean()
        ma60 = c.rolling(60).mean()
        last = float(c.iloc[-1])

        trend_up = bool(last > ma20.iloc[-1] and ma20.iloc[-1] > ma60.iloc[-1])
        # 최근 5거래일 내 20일선 상향 돌파 여부
        above = c > ma20
        cross_up = bool(above.iloc[-1] and not above.iloc[-6:-1].all())

        rows.append({
            "ticker": t,
            "name": s["name"],
            "close": round(last, 2),
            "r1": round(r1 * 100, 2),
            "r5": round(r5 * 100, 2),
            "r20": round(r20 * 100, 2),
            "rs": round((r20 - bench_r20) * 100, 2),
            "mom": 0.5 * r5 + 0.3 * r20 + 0.2 * r1,
            "_trend_up": trend_up,
            "_cross_up": cross_up,
            "_above_ma20": bool(last > ma20.iloc[-1]),
        })

    if not rows:
        return []

    rows.sort(key=lambda r: r["mom"], reverse=True)
    n = len(rows)
    top_cut = max(1, int(np.ceil(n * 0.30)))

    for i, r in enumerate(rows):
        r["rank"] = i + 1
        if not r["_above_ma20"]:
            sig = WEAK
        elif i < top_cut and r["rs"] > 0 and r["_trend_up"]:
            sig = STRONG
        elif r["_cross_up"]:
            sig = TURNING
        else:
            sig = NEUTRAL
        r["signal"] = sig
        r["signal_label"] = LABEL[sig]
        r["mom"] = round(r["mom"] * 100, 2)
        for k in ("_trend_up", "_cross_up", "_above_ma20"):
            r.pop(k)
    return rows

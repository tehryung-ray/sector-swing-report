# -*- coding: utf-8 -*-
"""미국 섹터 ETF 시세 수집 (yfinance)."""
from __future__ import annotations

import warnings

import pandas as pd

warnings.filterwarnings("ignore")

COLS = ["Open", "High", "Low", "Close", "Volume"]


def fetch_us(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """티커별 일봉 OHLCV. 실패한 티커는 결과에서 빠진다(호출부가 판단)."""
    import yfinance as yf

    raw = yf.download(
        tickers,
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
        group_by="ticker",
    )
    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            df = df[COLS].dropna(how="all")
            df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
            if len(df) >= 60:
                out[t] = df.sort_index()
        except (KeyError, ValueError):
            continue
    return out

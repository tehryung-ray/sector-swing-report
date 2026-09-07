# -*- coding: utf-8 -*-
"""한국 ETF 시세 수집 - 3단 폴백 + 캐시.

GitHub Actions 러너는 미국 IP다. data.krx.co.kr(pykrx)은 해외 IP에서 차단되거나
느려질 수 있고, pykrx 1.2.8+ 는 KRX 계정(KRX_ID/KRX_PW)까지 요구한다.
그래서 네이버 소스를 쓰는 FinanceDataReader 를 1순위로 둔다.
"""
from __future__ import annotations

import warnings
from datetime import timedelta

import pandas as pd

from ..util import CACHE_DIR

warnings.filterwarnings("ignore")

COLS = ["Open", "High", "Low", "Close", "Volume"]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df[[c for c in COLS if c in df.columns]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df.dropna(how="all").sort_index()


def _via_fdr(code: str, start: str) -> pd.DataFrame:
    import FinanceDataReader as fdr

    return _normalize(fdr.DataReader(code, start))


def _via_pykrx(code: str, start: str) -> pd.DataFrame:
    from pykrx import stock

    s = pd.Timestamp(start).strftime("%Y%m%d")
    e = pd.Timestamp.today().strftime("%Y%m%d")
    df = stock.get_etf_ohlcv_by_date(s, e, code)
    df = df.rename(
        columns={"시가": "Open", "고가": "High", "저가": "Low",
                 "종가": "Close", "거래량": "Volume"}
    )
    return _normalize(df)


def _via_yahoo(code: str, start: str) -> pd.DataFrame:
    import yfinance as yf

    df = yf.download(f"{code}.KS", start=start, interval="1d",
                     auto_adjust=False, progress=False, threads=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return _normalize(df)


SOURCES = [("fdr", _via_fdr), ("pykrx", _via_pykrx), ("yahoo", _via_yahoo)]


def _cache_path(code: str):
    return CACHE_DIR / "kr" / f"{code}.parquet"


def fetch_kr_one(code: str, start: str, min_rows: int = 80) -> tuple[pd.DataFrame | None, str]:
    """(df, source) 반환. 3단 폴백 후에도 실패하면 캐시를 쓴다."""
    for name, fn in SOURCES:
        try:
            df = fn(code, start)
            if df is not None and len(df) >= min_rows and df["Close"].notna().sum() >= min_rows:
                _write_cache(code, df)
                return df, name
        except Exception:
            continue

    p = _cache_path(code)
    if p.exists():
        try:
            return pd.read_parquet(p), "cache"
        except Exception:
            pass
    return None, "failed"


def _write_cache(code: str, df: pd.DataFrame) -> None:
    p = _cache_path(code)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)


def fetch_kr(codes: list[str], lookback_days: int = 400):
    """코드 목록을 수집한다. 반환: (데이터, 코드별 소스, 실패목록)"""
    start = (pd.Timestamp.today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    data, srcs, failed = {}, {}, []
    for c in codes:
        df, src = fetch_kr_one(c, start)
        srcs[c] = src
        if df is None:
            failed.append(c)
        else:
            data[c] = df
    return data, srcs, failed

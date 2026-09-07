# -*- coding: utf-8 -*-
"""공용 유틸 - 시간대, 호가단위, 안전 캐스팅."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache"
DOCS_DATA = ROOT / "docs" / "data"
CONFIG_DIR = ROOT / "config"


def now_kst() -> datetime:
    return datetime.now(KST)


def tick_size(price: float) -> int:
    """국내 ETF 호가단위. 2,000원 미만 1원, 그 이상 5원.

    이걸 적용하지 않으면 32,483원처럼 주문 자체가 불가능한 가격이 리포트에 찍힌다.
    """
    return 1 if price < 2000 else 5


def round_tick(price: float, mode: str = "nearest") -> int:
    """호가단위에 맞춰 정렬한다.

    mode: 'nearest' | 'down'(보수적 진입/익절) | 'up'(보수적 손절)
    """
    if price is None or not math.isfinite(price) or price <= 0:
        raise ValueError(f"round_tick: 유효하지 않은 가격 {price!r}")
    t = tick_size(price)
    q = price / t
    if mode == "down":
        n = math.floor(q)
    elif mode == "up":
        n = math.ceil(q)
    else:
        n = math.floor(q + 0.5)
    return int(n * t)


def pct(new: float, base: float) -> float:
    """base 대비 new 의 변화율(%). 소수점 2자리."""
    if base == 0:
        return 0.0
    return round((new / base - 1.0) * 100.0, 2)


def safe_float(x, default=None):
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default

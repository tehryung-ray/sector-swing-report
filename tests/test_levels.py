# -*- coding: utf-8 -*-
"""가격 산출 불변식 테스트.

여기서 지키는 것은 '리포트에 절대 나오면 안 되는 값'이다.
주문 불가 가격, 진입가 위의 손절, 손익비 왜곡 같은 것들.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.gates import MIN_RR, evaluate
from pipeline.levels import MAX_LOSS, MIN_LOSS, compute_levels
from pipeline.util import pct, round_tick, tick_size


def make_df(n=120, start=10000, drift=0.002, vol=0.01, seed=0):
    """합성 일봉 생성."""
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, vol, n)
    close = start * np.exp(np.cumsum(r))
    high = close * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.004, n)))
    return pd.DataFrame(
        {"Open": close, "High": high, "Low": low, "Close": close,
         "Volume": rng.integers(2_000_000, 8_000_000, n)},
        index=pd.bdate_range("2026-01-01", periods=n),
    )


# ---------- 호가단위 ----------

def test_tick_size_boundary():
    assert tick_size(1999) == 1
    assert tick_size(2000) == 5


@pytest.mark.parametrize("mode", ["nearest", "down", "up"])
def test_round_tick_is_orderable(mode):
    for p in (2345.6, 32483.0, 7181.2, 131_197.0):
        assert round_tick(p, mode) % 5 == 0, "2000원 이상은 5원 단위여야 주문 가능"


def test_round_tick_direction():
    assert round_tick(32483, "down") <= 32483 <= round_tick(32483, "up")


def test_round_tick_rejects_bad_input():
    for bad in (0, -1, float("nan"), None):
        with pytest.raises(ValueError):
            round_tick(bad)


# ---------- 가격 불변식 ----------

@pytest.mark.parametrize("seed", range(12))
def test_level_invariants(seed):
    lv = compute_levels(make_df(seed=seed, drift=0.002))
    assert lv is not None

    assert lv["stop"] < lv["entry"] < lv["tp1"] < lv["tp2"], "가격 순서가 깨졌다"
    assert lv["entry"] <= lv["last_close"], "진입가가 현재가보다 높을 수 없다"
    for k in ("entry", "tp1", "tp2", "stop"):
        assert lv[k] % 5 == 0, f"{k} 가 호가단위를 벗어났다"


@pytest.mark.parametrize("seed", range(12))
def test_stop_loss_is_capped(seed):
    """기획서의 -2~-3% 손절. 이 범위를 벗어나면 손익비가 왜곡된다."""
    lv = compute_levels(make_df(seed=seed))
    # 호가단위 반올림 여유 0.2%p
    assert -(MAX_LOSS * 100) - 0.2 <= lv["stop_pct"] <= -(MIN_LOSS * 100) + 0.2, \
        f"손절 {lv['stop_pct']}% 가 -3%~-2.5% 범위를 벗어남"


@pytest.mark.parametrize("seed", range(12))
def test_rr_matches_prices(seed):
    lv = compute_levels(make_df(seed=seed))
    expected = round((lv["tp1"] - lv["entry"]) / (lv["entry"] - lv["stop"]), 2)
    assert abs(lv["rr"] - expected) < 0.02


def test_pct_fields_consistent():
    lv = compute_levels(make_df(seed=3))
    assert lv["tp1_pct"] == pct(lv["tp1"], lv["entry"])
    assert lv["stop_pct"] == pct(lv["stop"], lv["entry"])


def test_short_history_returns_none():
    assert compute_levels(make_df(n=40)) is None
    assert compute_levels(None) is None


def test_downtrend_flagged():
    """하락 추세 종목은 kr_above_ma20 가 False 여야 게이트가 잡는다."""
    lv = compute_levels(make_df(drift=-0.004, seed=1))
    assert lv["kr_above_ma20"] is False


# ---------- 게이트 ----------

def base_levels():
    return {
        "last_close": 10000, "entry": 10000, "tp1": 10600, "tp2": 11000,
        "stop": 9720, "tp1_pct": 6.0, "tp2_pct": 10.0, "stop_pct": -2.8,
        "rr": 2.14, "dist_from_entry_pct": 0.0, "turnover_eok": 100.0,
        "ma20": 9800, "ma60": 9500, "kr_above_ma20": True, "kr_ma_stacked": True,
    }


def test_clean_setup_passes():
    assert evaluate(base_levels(), "strong") == []


def test_weak_us_sector_blocks():
    assert any("미국" in r for r in evaluate(base_levels(), "weak"))


def test_kr_downtrend_blocks():
    lv = base_levels() | {"kr_above_ma20": False}
    assert any("20일선 아래" in r for r in evaluate(lv, "strong"))


def test_low_rr_blocks():
    lv = base_levels() | {"rr": MIN_RR - 0.1}
    assert any("손익비" in r for r in evaluate(lv, "strong"))


def test_illiquid_blocks():
    lv = base_levels() | {"turnover_eok": 3.0}
    assert any("거래대금" in r for r in evaluate(lv, "strong"))


def test_far_entry_blocks():
    lv = base_levels() | {"dist_from_entry_pct": 9.9}
    assert any("대기" in r for r in evaluate(lv, "strong"))


def test_inverted_stop_blocks():
    lv = base_levels() | {"stop": 10100}
    assert any("손절가가 진입가 이상" in r for r in evaluate(lv, "strong"))

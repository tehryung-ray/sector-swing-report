# -*- coding: utf-8 -*-
"""가격 산출 불변식 테스트.

여기서 지키는 것은 '리포트에 절대 나오면 안 되는 값'이다.
주문 불가 가격, 진입가 위의 손절, 국면과 어긋나는 진입가 방향 같은 것들.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.gates import MIN_RR, MIN_TURNOVER_EOK, evaluate
from pipeline.levels import (BO_MAX_LOSS, BREAKOUT, DOWNTREND, EXTENDED,
                             EXTENDED_MAX, PB_MAX_LOSS, PULLBACK, compute_levels)
from pipeline.util import pct, round_tick, tick_size

TOL = 0.3  # 호가단위 반올림 여유(%p)


def make_df(n=140, start=10000, drift=0.002, vol=0.01, seed=0):
    rng = np.random.default_rng(seed)
    close = start * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    high = close * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.004, n)))
    return pd.DataFrame(
        {"Open": close, "High": high, "Low": low, "Close": close,
         "Volume": rng.integers(2_000_000, 8_000_000, n)},
        index=pd.bdate_range("2026-01-01", periods=n),
    )


ALL_SEEDS = list(range(16))


# ---------- 호가단위 ----------

def test_tick_size_boundary():
    assert tick_size(1999) == 1 and tick_size(2000) == 5


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


# ---------- 공통 불변식 ----------

@pytest.mark.parametrize("seed", ALL_SEEDS)
def test_price_ordering(seed):
    lv = compute_levels(make_df(seed=seed))
    assert lv is not None
    assert lv["stop"] < lv["entry"] < lv["tp1"] < lv["tp2"], "가격 순서가 깨졌다"
    for k in ("entry", "tp1", "tp2", "stop"):
        assert lv[k] % 5 == 0, f"{k} 가 호가단위를 벗어났다"


@pytest.mark.parametrize("seed", ALL_SEEDS)
def test_stop_never_exceeds_max_loss(seed):
    """어떤 국면에서도 1회 손실이 -3.5%를 넘지 않아야 한다."""
    lv = compute_levels(make_df(seed=seed))
    assert lv["stop_pct"] >= -(BO_MAX_LOSS * 100) - TOL, f"손절 {lv['stop_pct']}% 과다"


@pytest.mark.parametrize("seed", ALL_SEEDS)
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


# ---------- 국면 구분 ----------
# 이 전략의 핵심. 추세가 강하면 지지선에서 멀어지므로 진입 방식 자체가 바뀐다.

@pytest.mark.parametrize("seed", ALL_SEEDS)
def test_setup_matches_extension(seed):
    """국면은 20일선 이격도로 결정되며 라벨과 일치해야 한다."""
    lv = compute_levels(make_df(seed=seed))
    ext, setup = lv["ext_pct"], lv["setup"]
    if not lv["kr_above_ma20"]:
        assert setup == DOWNTREND
    elif ext > EXTENDED_MAX * 100:
        assert setup == EXTENDED
    elif ext <= 4.0:
        assert setup == PULLBACK
    else:
        assert setup == BREAKOUT


@pytest.mark.parametrize("seed", ALL_SEEDS)
def test_entry_direction_by_setup(seed):
    """눌림목형은 현재가 아래에서 기다리고, 돌파형은 현재가 위를 뚫을 때 산다."""
    lv = compute_levels(make_df(seed=seed))
    if lv["setup"] == PULLBACK:
        assert lv["entry"] <= lv["last_close"], "눌림목형 진입가가 현재가보다 높다"
        assert lv["entry_vs_last_pct"] <= 0.01
    elif lv["setup"] == BREAKOUT:
        assert lv["entry"] >= lv["last_close"], "돌파형 진입가가 현재가보다 낮다"


def test_pullback_stop_within_plan_range():
    """눌림목형 손절은 기획서의 -2~-3% 범위."""
    seen = 0
    for s in range(40):
        lv = compute_levels(make_df(seed=s, drift=0.0005, vol=0.008))
        if lv["setup"] == PULLBACK:
            seen += 1
            assert lv["stop_pct"] >= -(PB_MAX_LOSS * 100) - TOL
    assert seen > 0, "눌림목형 표본이 생성되지 않았다"


def test_breakout_targets_are_atr_based():
    for s in range(40):
        lv = compute_levels(make_df(seed=s, drift=0.004))
        if lv["setup"] == BREAKOUT:
            assert lv["target_basis"] == "ATR 투영"
            return
    pytest.fail("돌파형 표본이 생성되지 않았다")


def test_downtrend_detected():
    lv = compute_levels(make_df(drift=-0.004, seed=1))
    assert lv["setup"] == DOWNTREND and lv["kr_above_ma20"] is False


# ---------- 게이트 ----------

def base_levels(**over):
    lv = {
        "last_close": 10000, "entry": 10000, "tp1": 10600, "tp2": 11000,
        "stop": 9720, "tp1_pct": 6.0, "tp2_pct": 10.0, "stop_pct": -2.8,
        "rr": 2.14, "ext_pct": 2.0, "turnover_eok": 100.0,
        "ma20": 9800, "ma60": 9500, "setup": PULLBACK,
        "kr_above_ma20": True, "kr_ma_stacked": True, "kr_ma20_rising": True,
    }
    return lv | over


def test_clean_setup_passes():
    assert evaluate(base_levels(), "strong") == []


def test_weak_us_sector_blocks():
    assert any("미국" in r for r in evaluate(base_levels(), "weak"))


def test_downtrend_blocks():
    r = evaluate(base_levels(setup=DOWNTREND, kr_above_ma20=False), "strong")
    assert any("20일선 아래" in x for x in r)


def test_extended_blocks():
    r = evaluate(base_levels(setup=EXTENDED, ext_pct=15.0), "strong")
    assert any("과열" in x for x in r)


def test_rising_ma20_rescues_unstacked():
    """정배열이 아니어도 20일선이 상승 중이면 통과시킨다 (상승 전환 초기 포착)."""
    assert evaluate(base_levels(kr_ma_stacked=False, kr_ma20_rising=True), "strong") == []


def test_falling_unstacked_blocks():
    r = evaluate(base_levels(kr_ma_stacked=False, kr_ma20_rising=False), "strong")
    assert any("60일선" in x for x in r)


def test_low_rr_blocks():
    assert any("손익비" in r for r in evaluate(base_levels(rr=MIN_RR - 0.1), "strong"))


def test_illiquid_blocks():
    lv = base_levels(turnover_eok=MIN_TURNOVER_EOK - 1)
    assert any("거래대금" in r for r in evaluate(lv, "strong"))


def test_inverted_stop_blocks():
    r = evaluate(base_levels(stop=10100), "strong")
    assert any("손절가가 진입가 이상" in x for x in r)

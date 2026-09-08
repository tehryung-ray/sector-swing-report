# -*- coding: utf-8 -*-
"""복기 추적 테스트.

여기서 지키는 것은 '있지도 않은 성과를 기록하지 않는 것'이다.
체결되지 않은 추천을 체결로, 아직 결과를 알 수 없는 추천을 실패로 세면
복기 페이지 전체가 거짓말이 된다.
"""
from __future__ import annotations

import pandas as pd
import pytest

from pipeline.review import (CANCELLED, FILLED, NOT_FILLED, OPEN, STOPPED, TP1_TIME,
                             TP2, WAITING, reason_key, summarize, track_pick)

PICK = {"code": "X", "name": "테스트", "entry": 10000, "stop": 9700,
        "tp1": 10600, "tp2": 11000}
D0 = "2026-09-08"


def bars(rows):
    """[[시가, 고가, 저가, 종가], ...] -> 리포트 다음 거래일부터의 일봉."""
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"],
                        index=pd.bdate_range("2026-09-09", periods=len(rows)))


# ---------- 체결 판정 ----------

def test_no_data_is_waiting():
    """아직 장이 열리지 않았으면 '대기 중'이다. 미체결로 세면 체결률이 왜곡된다."""
    r = track_pick(PICK, bars([]), D0)
    assert r["fill"] == WAITING and r["pending"] is True


def test_not_filled_when_price_never_reaches_entry():
    r = track_pick(PICK, bars([[10200, 10400, 10100, 10300]]), D0)
    assert r["fill"] == NOT_FILLED and r["ret_pct"] is None


def test_cancelled_on_gap_down_below_stop():
    """시가가 손절가 아래로 열리면 주문을 취소한다 - 전략 규칙과 같아야 한다."""
    r = track_pick(PICK, bars([[9600, 9800, 9500, 9700]]), D0)
    assert r["fill"] == CANCELLED and r["ret_pct"] is None


def test_gap_down_fills_at_open_not_entry():
    """진입가 아래에서 열리면 시가에 체결된다. 진입가로 계산하면 성과가 부풀려진다."""
    r = track_pick(PICK, bars([[9900, 10700, 9850, 10500],
                               [10600, 11100, 10500, 11000]]), D0)
    assert r["fill_px"] == 9900


# ---------- 청산 판정 ----------

def test_stop_hit():
    r = track_pick(PICK, bars([[10000, 10100, 9650, 9700]]), D0)
    assert r["status"] == STOPPED
    assert r["ret_pct"] == pytest.approx(-3.0, abs=0.01)


def test_stop_is_checked_before_target():
    """하루에 손절과 익절을 모두 스치면 손절로 본다. 좋게 나오는 것보다 낫다."""
    r = track_pick(PICK, bars([[10000, 11200, 9600, 10800]]), D0)
    assert r["status"] == STOPPED


def test_split_exit_half_at_tp1_half_at_tp2():
    """설명서가 안내한 대로 1차에서 절반, 2차에서 나머지를 판다."""
    r = track_pick(PICK, bars([[10000, 10700, 9900, 10500],
                               [10600, 11100, 10500, 11000]]), D0)
    assert r["status"] == TP2
    expected = 0.5 * (10600 / 10000 - 1) + 0.5 * (11000 / 10000 - 1)
    assert r["ret_pct"] == pytest.approx(expected * 100, abs=0.02)
    assert [l["what"] for l in r["legs"]] == ["1차 익절", "2차 익절"]


def test_tp1_then_time_exit():
    flat = [10500, 10550, 10400, 10450]
    r = track_pick(PICK, bars([[10000, 10700, 9900, 10500]] + [flat] * 4), D0)
    assert r["status"] == TP1_TIME
    assert r["remain"] == 0.0


def test_still_open_before_max_hold():
    r = track_pick(PICK, bars([[10000, 10100, 9900, 10050],
                               [10050, 10150, 9950, 10100]]), D0)
    assert r["status"] == OPEN and r["pending"] is True


def test_max_hold_forces_exit():
    flat = [10000, 10100, 9900, 10050]
    r = track_pick(PICK, bars([flat] * 8), D0)
    assert r["pending"] is False and r["days"] == 5


# ---------- 집계 ----------

def test_waiting_excluded_from_fill_rate():
    """결과를 아직 물을 수 없는 건은 분모에서 빠져야 한다."""
    trades = [{"fill": WAITING, "pending": True},
              {"fill": FILLED, "pending": False, "ret_pct": 5.0, "status": TP2},
              {"fill": NOT_FILLED, "pending": False}]
    s = summarize(trades)
    assert s["waiting"] == 1 and s["tested"] == 2
    assert s["fill_rate"] == 50.0


def test_fill_rate_none_when_nothing_testable():
    s = summarize([{"fill": WAITING, "pending": True}])
    assert s["fill_rate"] is None and s["win_rate"] is None


def test_open_positions_not_counted_as_closed():
    trades = [{"fill": FILLED, "pending": True},
              {"fill": FILLED, "pending": False, "ret_pct": -2.0, "status": STOPPED}]
    s = summarize(trades)
    assert s["open"] == 1 and s["closed"] == 1 and s["win_rate"] == 0.0


# ---------- 관망 사유 정규화 ----------

@pytest.mark.parametrize("msg,want", [
    ("미국 매핑 섹터가 하락세", "미국 섹터가 하락세"),
    ("20일선이 60일선 아래이고 방향도 하락", "중기 추세 미회복"),
    ("국내 종목이 20일선 아래 (종가 8,175 < MA20 8,590)", "국내 20일선 아래"),
    ("20일선 이격 +15.85% 과열 (기준 12% 초과)", "20일선 이격 과열"),
    ("손익비 0.84 (최소 1.5 미달)", "손익비 미달"),
    ("거래대금 3.2억 (최소 5.0억 미달)", "거래대금 부족"),
])
def test_reason_key(msg, want):
    """숫자가 섞인 사유를 그대로 묶으면 표본이 1~2건으로 흩어진다."""
    assert reason_key(msg) == want

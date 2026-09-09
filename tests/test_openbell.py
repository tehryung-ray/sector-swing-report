# -*- coding: utf-8 -*-
"""개장 점검 판정 테스트.

여기서 지키는 것은 '해야 할 일을 놓치지 않는 것'과 '없는 일을 만들지 않는 것'이다.
체결됐는데 알림이 안 오면 손절 주문을 못 걸고, 할 일 없는 날 알림이 오면 무뎌진다.
"""
from __future__ import annotations

import pytest

from pipeline.openbell import (CANCEL, FILLED, INVALID, WAITING, build_message,
                               judge)

PICK = {"code": "X", "name": "테스트", "entry": 10000, "stop": 9700,
        "tp1": 10600, "tp2": 11000, "cancel_below": 9700}
REP = {"report_date": "2026-09-09"}


def bar(o, h, l, c):
    return {"Open": o, "High": h, "Low": l, "Close": c}


def test_gap_down_below_cancel_line():
    r = judge(PICK, bar(9600, 9800, 9500, 9650))
    assert r["state"] == CANCEL


def test_cancel_takes_priority_over_fill():
    """취소 대상이면 체결 여부를 따지지 않는다. 애초에 주문을 냈으면 안 될 자리다."""
    r = judge(PICK, bar(9600, 10100, 9500, 10000))   # 저가가 진입가 아래이기도 하다
    assert r["state"] == CANCEL


def test_filled_when_low_touches_entry():
    r = judge(PICK, bar(10100, 10200, 9950, 10050))
    assert r["state"] == FILLED
    assert r["fill"] == 10000
    assert r["pnl_pct"] == pytest.approx(0.5, abs=0.01)


def test_gap_down_above_cancel_fills_at_open():
    """진입가 아래·취소선 위에서 열리면 시가에 체결된다."""
    r = judge(PICK, bar(9800, 10100, 9750, 9900))
    assert r["state"] == FILLED and r["fill"] == 9800


def test_waiting_when_never_reaches_entry():
    r = judge(PICK, bar(10300, 10500, 10150, 10400))
    assert r["state"] == WAITING


def test_missing_bar_is_invalid_not_waiting():
    """시세를 못 가져온 것을 미체결로 처리하면 체결된 종목을 놓친다."""
    assert judge(PICK, None)["state"] == INVALID


# ---------- 메시지 ----------

def test_no_message_when_nothing_to_do():
    rows = [judge(PICK, bar(10300, 10500, 10150, 10400))]      # 미체결뿐
    assert build_message(REP, rows) is None


def test_message_lists_cancel_and_fill():
    rows = [judge(PICK, bar(9600, 9800, 9500, 9650)),
            judge({**PICK, "name": "다른종목"}, bar(10100, 10200, 9950, 10050))]
    m = build_message(REP, rows)
    assert "예약주문 취소 1건" in m and "체결 1건" in m
    assert "테스트" in m and "다른종목" in m


def test_message_warns_about_stoploss_order_type():
    """손절을 지정가로 걸면 즉시 팔린다. 이 경고가 빠지면 안 된다."""
    rows = [judge(PICK, bar(10100, 10200, 9950, 10050))]
    m = build_message(REP, rows)
    assert "스탑로스" in m


def test_invalid_alone_sends_nothing():
    assert build_message(REP, [judge(PICK, None)]) is None


def test_all_invalid_during_market_hours_warns():
    """09:10 에 전 종목 시세 실패면 조용히 넘어가면 안 된다. 취소할 주문을 놓친다."""
    rows = [judge(PICK, None), judge({**PICK, "name": "다른종목"}, None)]
    m = build_message(REP, rows, market_open=True)
    assert m is not None and "실패" in m


def test_all_invalid_before_market_stays_silent():
    """장 시작 전 수동 실행에서는 시세가 없는 게 정상이므로 보내지 않는다."""
    assert build_message(REP, [judge(PICK, None)], market_open=False) is None


def test_partial_invalid_is_noted_in_message():
    rows = [judge(PICK, bar(10100, 10200, 9950, 10050)),
            judge({**PICK, "name": "시세없음"}, None)]
    m = build_message(REP, rows, market_open=True)
    assert "체결 1건" in m and "시세없음" in m


# ---------- 워크플로 입력 판정 ----------

@pytest.mark.parametrize("val,want", [
    ("true", True), ("1", True), ("TRUE", True), ("on", True), ("yes", True),
    ("false", False), ("0", False), ("", False), ("  ", False),
])
def test_flag_parsing(monkeypatch, val, want):
    """'false' 는 파이썬에서 참인 문자열이다. 그대로 쓰면 반대로 동작한다."""
    from pipeline.check_open import flag
    monkeypatch.setenv("X", val)
    assert flag("X") is want


def test_flag_missing_env_is_false(monkeypatch):
    from pipeline.check_open import flag
    monkeypatch.delenv("X", raising=False)
    assert flag("X") is False


def test_flag_checks_multiple_names(monkeypatch):
    """inputs / github.event.inputs 어느 쪽으로 와도 받아야 한다."""
    from pipeline.check_open import flag
    monkeypatch.setenv("A", "")
    monkeypatch.setenv("B", "true")
    assert flag("A", "B") is True


# ---------- 중복 발송 방지 ----------

def _rows(*states):
    """상태 목록으로 판정 결과 흉내내기."""
    out = []
    for i, st in enumerate(states):
        if st == CANCEL:
            out.append(judge({**PICK, "code": f"C{i}"}, bar(9600, 9800, 9500, 9650)))
        elif st == FILLED:
            out.append(judge({**PICK, "code": f"C{i}"}, bar(10100, 10200, 9950, 10050)))
        else:
            out.append(judge({**PICK, "code": f"C{i}"}, bar(10300, 10500, 10150, 10400)))
    return out


def test_same_content_not_resent():
    """크론을 여러 번 걸면 같은 알림이 반복된다. 두 번째부터는 보내지 않는다."""
    from pipeline.openbell import should_send, _digest
    rows = _rows(CANCEL, WAITING)
    state = {"date": "2026-09-10", "digest": _digest(rows)}
    go, why = should_send(state, "2026-09-10", rows)
    assert go is False and "이미" in why


def test_changed_content_is_resent():
    """09:10 에 취소만 있다가 09:30 에 체결이 생기면 새 정보이므로 다시 보낸다."""
    from pipeline.openbell import should_send, _digest
    first = _rows(CANCEL, WAITING)
    later = _rows(CANCEL, FILLED)
    state = {"date": "2026-09-10", "digest": _digest(first)}
    go, why = should_send(state, "2026-09-10", later)
    assert go is True and "바뀌" in why


def test_new_day_resets():
    from pipeline.openbell import should_send, _digest
    rows = _rows(CANCEL)
    state = {"date": "2026-09-09", "digest": _digest(rows)}
    assert should_send(state, "2026-09-10", rows)[0] is True


def test_nothing_actionable_never_sends():
    from pipeline.openbell import should_send
    go, why = should_send({}, "2026-09-10", _rows(WAITING, WAITING))
    assert go is False and "없음" in why


def test_digest_ignores_non_actionable():
    """미체결이 섞여도 취소·체결 구성이 같으면 같은 내용으로 본다."""
    from pipeline.openbell import _digest
    assert _digest(_rows(CANCEL, WAITING)) == _digest(_rows(CANCEL, WAITING))
    assert _digest(_rows(CANCEL)) != _digest(_rows(CANCEL, FILLED))


def test_save_and_load_roundtrip(tmp_path):
    from pipeline.openbell import save_state, load_state, should_send
    p = tmp_path / "openbell.json"
    rows = _rows(CANCEL, FILLED)
    save_state(p, "2026-09-10", rows, True)
    assert should_send(load_state(p), "2026-09-10", rows)[0] is False


def test_load_missing_file_is_empty():
    from pathlib import Path
    from pipeline.openbell import load_state
    assert load_state(Path("없는파일.json")) == {}

# -*- coding: utf-8 -*-
"""관망 판정 게이트. 하나라도 걸리면 추천하지 않는다."""
from __future__ import annotations

from .momentum import WEAK

MIN_RR = 1.5             # 최소 손익비
MIN_TURNOVER_EOK = 10.0   # 20일 평균 거래대금 10억원
MIN_UPSIDE_PCT = 2.0      # 1차 익절까지 최소 2%
MAX_WAIT_PCT = 5.0        # 진입가까지 5% 넘게 기다려야 하면 스윙 기간 내 체결 난망


def evaluate(lv: dict, us_signal: str) -> list[str]:
    """통과하면 빈 리스트, 아니면 관망 사유 목록."""
    reasons = []

    # 1. 미국 선행 섹터가 죽어 있으면 국내도 안 본다
    if us_signal == WEAK:
        reasons.append("미국 매핑 섹터가 하락세")

    # 2. 국내 종목 자체가 상승 추세여야 한다 (하락 종목 저점 매수 방지)
    if not lv["kr_above_ma20"]:
        reasons.append(f"국내 종목이 20일선 아래 (종가 {lv['last_close']:,} < MA20 {lv['ma20']:,})")
    elif not lv["kr_ma_stacked"]:
        reasons.append(f"20일선이 60일선 아래 (중기 추세 미회복)")

    # 3. 먹을 폭이 있어야 한다
    if lv["tp1"] <= lv["entry"]:
        reasons.append("1차 익절가가 진입가 이하")
    elif lv["tp1_pct"] < MIN_UPSIDE_PCT:
        reasons.append(f"1차 익절까지 {lv['tp1_pct']}% (최소 {MIN_UPSIDE_PCT}% 미달)")

    # 4. 손익비
    if lv["stop"] >= lv["entry"]:
        reasons.append("손절가가 진입가 이상 (계산 이상)")
    elif lv["rr"] < MIN_RR:
        reasons.append(f"손익비 {lv['rr']} (최소 {MIN_RR} 미달)")

    # 5. 유동성
    if lv["turnover_eok"] < MIN_TURNOVER_EOK:
        reasons.append(f"거래대금 {lv['turnover_eok']}억 (최소 {MIN_TURNOVER_EOK}억 미달)")

    # 6. 진입가까지 대기폭
    if lv["dist_from_entry_pct"] > MAX_WAIT_PCT:
        reasons.append(f"진입가까지 -{lv['dist_from_entry_pct']}% 대기 필요 (체결 난망)")

    return reasons

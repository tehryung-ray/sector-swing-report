# -*- coding: utf-8 -*-
"""관망 판정 게이트. 하나라도 걸리면 추천하지 않는다.

기준값 조정 이력 (2026-09-08)
  손익비      1.5 -> 1.2   2~5일 스윙에서 1.5는 과도. 손절 -3% 기준 익절 +3.6%면 유효.

기준값 재조정 (2026-09-08, 워크포워드 최적화)
  손익비      1.2 -> 1.5   되돌림. 실측이 1.2 를 지지하지 않았다.
                          워크포워드 6개 폴드 전부, 훈련 상위 30개 중 18개에서 1.5 가 선택됐다.
                          완전 격리 검증(2021~2026)에서 거래당 기대값 +0.212% -> +0.366%.
                          거래는 15% 줄지만 남는 거래의 질이 그만큼 좋아진다.
  거래대금     10 -> 5억    개인 스윙 규모에 5억이면 충분. 10억은 정상 종목까지 잘랐다.
  최소 상승폭  2.0 -> 1.5%  1차 익절은 분할매도 지점이므로 낮아도 된다.
  대기폭 5%   -> 삭제       levels 의 국면 구분(눌림목/돌파)이 대체한다.
  20>60일선   완화          '또는 20일선이 상승 중'을 허용. 상승 전환 초기를 놓치지 않기 위함.
"""
from __future__ import annotations

from .levels import DOWNTREND, EXTENDED, EXTENDED_MAX
from .momentum import WEAK

MIN_RR = 1.5
MIN_TURNOVER_EOK = 5.0
MIN_UPSIDE_PCT = 1.5


def evaluate(lv: dict, us_signal: str) -> list[str]:
    """통과하면 빈 리스트, 아니면 관망 사유 목록."""
    reasons = []

    # 1. 미국 선행 섹터가 죽어 있으면 국내도 보지 않는다 (전략의 대전제)
    if us_signal == WEAK:
        reasons.append("미국 매핑 섹터가 하락세")

    # 2. 국면: 하락추세 / 과열은 진입 자체가 성립하지 않는다
    if lv["setup"] == DOWNTREND:
        reasons.append(f"국내 종목이 20일선 아래 (종가 {lv['last_close']:,} < MA20 {lv['ma20']:,})")
    elif lv["setup"] == EXTENDED:
        reasons.append(f"20일선 이격 +{lv['ext_pct']}% 과열 (기준 {EXTENDED_MAX*100:.0f}% 초과)")

    # 3. 중기 추세: 정배열이거나, 최소한 20일선이 상승 중이어야 한다
    if lv["kr_above_ma20"] and not (lv["kr_ma_stacked"] or lv["kr_ma20_rising"]):
        reasons.append("20일선이 60일선 아래이고 방향도 하락")

    # 4. 먹을 폭
    if lv["tp1"] <= lv["entry"]:
        reasons.append("1차 익절가가 진입가 이하")
    elif lv["tp1_pct"] < MIN_UPSIDE_PCT:
        reasons.append(f"1차 익절까지 {lv['tp1_pct']}% (최소 {MIN_UPSIDE_PCT}% 미달)")

    # 5. 손익비
    if lv["stop"] >= lv["entry"]:
        reasons.append("손절가가 진입가 이상 (계산 이상)")
    elif lv["rr"] < MIN_RR:
        reasons.append(f"손익비 {lv['rr']} (최소 {MIN_RR} 미달)")

    # 6. 유동성
    if lv["turnover_eok"] < MIN_TURNOVER_EOK:
        reasons.append(f"거래대금 {lv['turnover_eok']}억 (최소 {MIN_TURNOVER_EOK}억 미달)")

    return reasons


# 같은 미국 섹터에 묶인 국내 ETF는 서로 상관이 0.94~0.99 로 사실상 같은 종목이다
# (TIGER 반도체TOP10 x KODEX 반도체 = 0.976, 다른 섹터끼리는 중앙값 0.472).
# 여러 개를 담으면 분산이 아니라 한 종목을 여러 배로 산 것이 된다.
#
# 검증(2021~2026, 3,000만원·슬롯 5·위험 0.5%):
#   제한없음  연 +6.7% / MDD 23.1%  (수익/MDD 0.29)
#   1종목     연 +6.0% / MDD 16.2%  (수익/MDD 0.37)
# 수익은 0.7%p 줄지만 낙폭이 7%p 가까이 개선된다. 6개 연도 중 5개에서 MDD 개선.
# 2종목 제한은 탈락이 9건뿐이라 사실상 무제한과 같아 의미가 없다.
MAX_PER_SECTOR = 1


def apply_sector_cap(picks: list[dict], limit: int = MAX_PER_SECTOR):
    """미국 섹터당 상위 종목만 남기고 나머지는 관망으로 내린다.

    picks 는 신호 강도·손익비 순으로 이미 정렬돼 있다고 가정한다.
    반환: (남길 추천, 관망으로 내릴 종목)
    """
    kept, dropped, taken = [], [], {}
    for p in picks:
        t = p.get("us_ticker")
        if len(taken.get(t, [])) >= limit:
            first = taken[t][0]
            reason = f"같은 섹터에서 {first} 선택됨 (상관 0.9 이상, 분산 효과 없음)"
            dropped.append({**p, "reasons": [reason]})
        else:
            taken.setdefault(t, []).append(p["name"])
            kept.append(p)
    return kept, dropped

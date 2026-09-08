# -*- coding: utf-8 -*-
"""뉴스 태깅 테스트. 네트워크 없이 순수 함수만 검증한다."""
from __future__ import annotations

from pipeline.news import (NEG, NEU, POS, TILT_MARGIN, _split_source,
                           is_market_related, summarize, tag_tone)


def test_clear_positive():
    tone, why = tag_tone("반도체 훈풍에 관련 소부장주 급등")
    assert tone == POS and why


def test_clear_negative():
    assert tag_tone("실적 쇼크에 주가 급락")[0] == NEG


def test_mixed_becomes_neutral():
    """긍정/부정 어휘가 같은 수면 단정하지 않는다."""
    assert tag_tone("반도체 급등에도 개인 계좌는 손실")[0] == NEU


def test_ambiguous_words_removed():
    """'감소/증가/확대/축소'는 맥락에 따라 뜻이 뒤집혀 사전에서 제외했다."""
    assert tag_tone("원유 재고 4억배럴 감소…국제유가 100달러 눈앞")[0] == NEU
    for w in ("감소", "증가", "확대", "축소"):
        assert tag_tone(f"업황 {w}")[0] == NEU


def test_market_relevance_filter():
    assert is_market_related("현대로템 주가 상승 중")
    assert not is_market_related("현대로템, 첫 항공우주 특화 채용 진행")


def test_split_source():
    t, s = _split_source("반도체 반등에 ETF 수익률 쑥 - 연합뉴스")
    assert t == "반도체 반등에 ETF 수익률 쑥" and s == "연합뉴스"
    t, s = _split_source("제목만 있는 기사")
    assert t == "제목만 있는 기사" and s == ""


def _items(p, n, u):
    return [{"tone": POS}] * p + [{"tone": NEG}] * n + [{"tone": NEU}] * u


def test_tilt_requires_margin():
    """1건 차이로 섹터 성향을 단정하면 오분류가 그대로 결론이 된다."""
    assert summarize(_items(0, 1, 4))["tilt"] == NEU
    assert summarize(_items(2, 2, 1))["tilt"] == NEU
    assert summarize(_items(TILT_MARGIN, 0, 0))["tilt"] == POS
    assert summarize(_items(0, TILT_MARGIN, 0))["tilt"] == NEG


def test_summarize_counts():
    s = summarize(_items(2, 1, 3))
    assert (s["count"], s["positive"], s["negative"], s["neutral"]) == (6, 2, 1, 3)


def test_empty_is_neutral():
    s = summarize([])
    assert s["count"] == 0 and s["tilt"] == NEU

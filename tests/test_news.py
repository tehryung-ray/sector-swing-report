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


SECTORS = [{"ticker": "XLE", "name": "에너지", "news_kw": "국제유가"}]
FAKE_ITEM = {"title": "원유 재고 감소", "tone": NEU, "tone_label": "중립", "keywords": []}


def _stub_fetch(monkeypatch, items):
    from pipeline import news
    monkeypatch.setattr(news, "fetch_sector_news",
                        lambda kw, limit=5, days=3: [dict(i) for i in items])


def test_llm_disabled_without_key(monkeypatch):
    """키가 없으면 LLM 을 호출하지 않고 사전 분류를 유지한다."""
    from pipeline import llm, news
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _stub_fetch(monkeypatch, [FAKE_ITEM])
    assert llm.is_enabled() is False
    out, warns = news.collect(SECTORS)
    assert out["XLE"]["summary"]["classifier"] == "keyword"
    assert warns == []


def test_llm_result_overrides_keyword(monkeypatch):
    """LLM 이 응답하면 사전 분류를 덮어쓰고 분류기 이름을 남긴다."""
    from pipeline import llm, news
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    monkeypatch.setattr(llm, "model_name", lambda: "gemini-test")
    monkeypatch.setattr(llm, "classify_all",
                        lambda groups: ({0: [{"tone": POS, "reason": "재고 감소는 호재"}]}, []))
    _stub_fetch(monkeypatch, [FAKE_ITEM])
    out, warns = news.collect(SECTORS)
    assert out["XLE"]["summary"]["classifier"] == "gemini:gemini-test"
    it = out["XLE"]["items"][0]
    assert it["tone"] == POS and it["keywords"] == ["재고 감소는 호재"]


def test_llm_failure_surfaces_warning(monkeypatch):
    """분류 실패는 조용히 넘어가지 않고 이유가 경고로 올라와야 한다."""
    from pipeline import llm, news
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    monkeypatch.setattr(llm, "classify_all", lambda groups: ({}, ["HTTP 429 (에너지)"]))
    _stub_fetch(monkeypatch, [FAKE_ITEM])
    out, warns = news.collect(SECTORS)
    assert out["XLE"]["summary"]["classifier"] == "keyword"
    assert warns == ["HTTP 429 (에너지)"]


def test_chunking_reduces_calls():
    """18섹터를 섹터당 1회로 쏘면 분당 제한에 걸린다. 묶어서 호출 수를 줄인다."""
    from pipeline import llm
    calls = -(-18 // llm.CHUNK)
    assert calls <= 4, f"18섹터에 {calls}회 호출은 분당 제한 위험"


def test_empty_is_neutral():
    s = summarize([])
    assert s["count"] == 0 and s["tilt"] == NEU

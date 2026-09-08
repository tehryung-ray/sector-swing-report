# -*- coding: utf-8 -*-
"""섹터별 뉴스 이슈 수집 및 긍정/부정 성향 태깅.

한계를 먼저 밝힌다. 여기 붙는 긍정/부정 라벨은 **헤드라인 키워드 사전** 기반이다.
문맥을 읽지 못하므로 반어법, 복합 문장, 시장 전체 얘기와 종목 얘기를 구분하지 못한다.
예: "반도체 반등에 ETF 수익률 쑥, 개인은 차익실현" -> 긍정/부정 어휘가 동시에 등장.

따라서 이 값은 **매매 판단 근거가 아니라 읽을거리 우선순위**로만 쓴다.
가격 신호(모멘텀/국면)는 시세로 계산한 값이고, 뉴스 태그는 참고용이다.
화면에도 그렇게 표기한다.

GEMINI_API_KEY 가 환경변수에 있으면 Gemini 로 분류 품질을 올린다(선택).
없거나 호출이 실패하면 사전 방식으로 자동 폴백한다. 어느 쪽을 썼는지는
summary["classifier"] 로 데이터에 남겨 화면에서 신뢰도를 구분해 보여준다.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from . import llm
from .util import KST

RSS = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
UA = "Mozilla/5.0 (compatible; sector-invest-report/1.0)"
TIMEOUT = 15

POSITIVE = [
    "급등", "상승", "강세", "호재", "신고가", "최고가", "수주", "계약", "흑자", "개선",
    "회복", "반등", "돌파", "성장", "순매수", "상향", "훈풍", "랠리",
    "사상 최대", "역대급", "수혜", "호실적", "질주", "급증", "기대감", "낙관", "선전",
]
NEGATIVE = [
    "급락", "하락", "약세", "악재", "신저가", "부진", "적자", "우려",
    "리스크", "규제", "제재", "하향", "충격", "폭락", "둔화", "순매도", "손실",
    "위기", "침체", "철회", "무산", "하회", "발목", "먹구름", "쇼크", "적신호",
]

# 증시 무관 기사 배제용. OR 쿼리는 결과가 넓어서 채용/정책 기사까지 딸려온다.
MARKET_TERMS = [
    "주가", "증시", "코스피", "코스닥", "종목", "주식", "ETF", "실적", "전망",
    "목표주가", "시총", "매수", "매도", "투자", "상장", "배당", "어닝", "수익률",
    "밸류", "펀드", "지수", "장중", "개미", "외국인", "기관",
]

POS, NEG, NEU = "positive", "negative", "neutral"
TONE_LABEL = {POS: "긍정", NEG: "부정", NEU: "중립"}


def is_market_related(title: str) -> bool:
    """증시 맥락이 없는 기사는 버린다."""
    return any(w in title for w in MARKET_TERMS + POSITIVE + NEGATIVE)


def tag_tone(title: str) -> tuple[str, list[str]]:
    """헤드라인에서 감성 어휘를 찾아 성향을 매긴다. (성향, 근거어휘)"""
    hits_p = [w for w in POSITIVE if w in title]
    hits_n = [w for w in NEGATIVE if w in title]
    if len(hits_p) > len(hits_n):
        return POS, hits_p[:3]
    if len(hits_n) > len(hits_p):
        return NEG, hits_n[:3]
    return NEU, (hits_p + hits_n)[:3]


def _split_source(title: str) -> tuple[str, str]:
    """구글뉴스 제목 끝의 ' - 언론사' 를 분리한다."""
    m = re.match(r"^(.*)\s+-\s+([^-]{2,25})$", title.strip())
    return (m.group(1).strip(), m.group(2).strip()) if m else (title.strip(), "")


def fetch_sector_news(keyword: str, limit: int = 5, days: int = 3) -> list[dict]:
    """섹터 키워드로 최근 뉴스를 가져온다. 실패하면 빈 리스트(리포트는 계속 생성)."""
    q = urllib.parse.quote(keyword)
    try:
        req = urllib.request.Request(RSS.format(q=q), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            root = ET.fromstring(r.read())
    except Exception:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out, seen = [], set()
    for it in root.findall(".//item"):
        raw = (it.findtext("title") or "").strip()
        if not raw:
            continue
        title, source = _split_source(raw)
        if not is_market_related(title):
            continue
        key = re.sub(r"\W+", "", title)[:40]
        if key in seen:
            continue
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate"))
            if pub < cutoff:
                continue
        except (TypeError, ValueError):
            continue
        seen.add(key)
        tone, why = tag_tone(title)
        out.append({
            "title": title,
            "source": source,
            "link": it.findtext("link") or "",
            "published_kst": pub.astimezone(KST).strftime("%m-%d %H:%M"),
            "tone": tone,
            "tone_label": TONE_LABEL[tone],
            "keywords": why,
        })
        if len(out) >= limit:
            break
    return out


# 긍정/부정 기사 수 차이가 이만큼 나야 섹터 성향을 단정한다.
# 1건 차이로 '부정 섹터'라고 부르면 사전 방식의 오분류가 그대로 결론이 된다.
TILT_MARGIN = 2


def summarize(items: list[dict]) -> dict:
    """섹터 단위 이슈 요약."""
    p = sum(1 for i in items if i["tone"] == POS)
    n = sum(1 for i in items if i["tone"] == NEG)
    if p - n >= TILT_MARGIN:
        tilt = POS
    elif n - p >= TILT_MARGIN:
        tilt = NEG
    else:
        tilt = NEU
    return {
        "count": len(items),
        "positive": p, "negative": n, "neutral": len(items) - p - n,
        "tilt": tilt, "tilt_label": TONE_LABEL[tilt],
    }


def _relabel(items: list[dict], res: list[dict]) -> None:
    for item, r in zip(items, res):
        item["tone"] = r["tone"]
        item["tone_label"] = TONE_LABEL[r["tone"]]
        item["keywords"] = [r["reason"]] if r["reason"] else []


def collect(sectors: list[dict], limit: int = 5, days: int = 3) -> tuple[dict[str, dict], list[str]]:
    """섹터 설정 목록 -> ({ticker: {items, summary}}, 경고 메시지 목록)

    뉴스를 모두 모은 뒤 LLM 분류를 한 번에 처리한다. 섹터마다 따로 호출하면
    무료 티어 분당 제한에 걸려 뒤쪽 섹터가 조용히 사전 분류로 떨어진다.
    """
    fetched = []
    for s in sectors:
        kw = s.get("news_kw") or s.get("name")
        fetched.append((s["ticker"], s.get("name", kw), kw,
                        fetch_sector_news(kw, limit=limit, days=days)))

    warnings: list[str] = []
    llm_res: dict[int, list[dict]] = {}
    if llm.is_enabled():
        llm_res, errs = llm.classify_all([(name, [i["title"] for i in items])
                                          for _, name, _, items in fetched])
        warnings.extend(errs)

    out = {}
    for gi, (ticker, name, kw, items) in enumerate(fetched):
        if gi in llm_res:
            _relabel(items, llm_res[gi])
            classifier = f"gemini:{llm.model_name()}"
        else:
            classifier = "keyword"
        out[ticker] = {
            "keyword": kw,
            "items": items,
            "summary": summarize(items) | {"classifier": classifier},
        }
    return out, warnings

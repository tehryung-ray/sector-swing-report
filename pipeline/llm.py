# -*- coding: utf-8 -*-
"""Gemini 기반 뉴스 성향 분류 (선택 기능).

키워드 사전은 문맥을 못 읽는다. "원유 재고 감소"는 에너지 섹터에 호재지만
사전은 '감소'만 보고 부정으로 찍는다. LLM은 섹터를 알려주면 이걸 구분한다.

- GEMINI_API_KEY 가 없으면 아무것도 하지 않고 None 을 반환한다 -> 호출부가 사전으로 폴백.
- SDK 를 쓰지 않고 REST 로 호출한다. 의존성을 늘리지 않고 Actions 에서도 그대로 돈다.
- 섹터당 1회 호출로 헤드라인을 묶어 분류한다 (저렴한 모델 + 배치).
- 어떤 실패(키 오류/쿼터/타임아웃/응답 파손)든 None 을 돌려주고 리포트는 계속 생성한다.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# 저가 티어. 필요하면 GEMINI_MODEL 로 교체 가능.
DEFAULT_MODEL = "gemini-2.5-flash-lite"
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT = 25

TONE_MAP = {"긍정": "positive", "부정": "negative", "중립": "neutral"}

PROMPT = """너는 한국 주식 시장 뉴스를 분류하는 도구다.

아래는 '{sector}' 섹터 관련 뉴스 헤드라인이다.
각 헤드라인이 **이 섹터에 속한 종목의 주가에 미치는 영향**을 기준으로 분류하라.

판단 기준:
- 긍정: 이 섹터 주가에 호재
- 부정: 이 섹터 주가에 악재
- 중립: 영향이 불분명하거나 단순 사실 전달

주의:
- 어휘가 아니라 맥락으로 판단하라. 예를 들어 '원유 재고 감소'는 에너지 섹터에 호재다.
- 다른 섹터에 대한 호재/악재는 이 섹터 기준으로는 중립일 수 있다.
- reason 은 15자 이내 한국어로 간결하게.

헤드라인:
{headlines}

각 헤드라인에 대해 index(0부터), tone(긍정/부정/중립), reason 을 JSON 배열로 반환하라."""

SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "index": {"type": "INTEGER"},
            "tone": {"type": "STRING", "enum": ["긍정", "부정", "중립"]},
            "reason": {"type": "STRING"},
        },
        "required": ["index", "tone", "reason"],
    },
}


def is_enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def model_name() -> str:
    return os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)


def classify(titles: list[str], sector: str) -> list[dict] | None:
    """헤드라인 목록을 섹터 관점에서 분류한다.

    반환: [{"tone": "positive"|"negative"|"neutral", "reason": str}, ...] (titles 와 같은 길이)
          실패 시 None.
    """
    key = os.environ.get("GEMINI_API_KEY")
    if not key or not titles:
        return None

    body = {
        "contents": [{"parts": [{"text": PROMPT.format(
            sector=sector,
            headlines="\n".join(f"{i}. {t}" for i, t in enumerate(titles)),
        )}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
        },
    }
    req = urllib.request.Request(
        ENDPOINT.format(model=model_name()),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            payload = json.loads(r.read())
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            KeyError, IndexError, ValueError, TypeError):
        return None

    out = [{"tone": "neutral", "reason": ""} for _ in titles]
    if not isinstance(parsed, list):
        return None
    for item in parsed:
        try:
            i = int(item["index"])
            if 0 <= i < len(titles):
                out[i] = {
                    "tone": TONE_MAP.get(str(item.get("tone")), "neutral"),
                    "reason": str(item.get("reason", ""))[:40],
                }
        except (KeyError, TypeError, ValueError):
            continue
    return out

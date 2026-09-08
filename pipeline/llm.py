# -*- coding: utf-8 -*-
"""Gemini 기반 뉴스 성향 분류 (선택 기능).

키워드 사전은 문맥을 못 읽는다. "원유 재고 감소"는 에너지 섹터에 호재지만
사전은 '감소'만 보고 부정으로 찍는다. LLM은 섹터를 알려주면 이걸 구분한다.

## 왜 묶어서 보내는가
섹터마다 1회씩 18회를 연속 호출하면 무료 티어 분당 제한(약 15 RPM)에 걸려
뒤쪽 섹터가 429 로 잘린다. 실제로 첫 배포에서 18개 중 6개가 이렇게 폴백했다.
그래서 여러 섹터를 한 요청에 묶어 보낸다(기본 6개씩 = 하루 3회 호출).
한 청크가 실패해도 그 청크만 사전 방식으로 떨어지고 나머지는 살아남는다.

## 실패는 조용히 넘어가지 않는다
어떤 실패든 사전 방식으로 폴백하되, 이유를 문자열로 돌려준다.
호출부가 그걸 로그에 남겨야 '왜 AI 분류가 아니지?'를 다시 헤매지 않는다.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_MODEL = "gemini-2.5-flash-lite"
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT = 40
CHUNK = 6           # 한 요청에 담을 섹터 수
RETRIES = 3         # 429/5xx 재시도 횟수
BACKOFF = 8         # 재시도 대기 기준(초). 분당 제한이라 넉넉히 잡는다.

TONE_MAP = {"긍정": "positive", "부정": "negative", "중립": "neutral"}

PROMPT = """너는 한국 주식 시장 뉴스를 분류하는 도구다.

아래에 여러 섹터의 뉴스 헤드라인이 있다.
각 헤드라인이 **그 헤드라인이 속한 섹터의 종목 주가에 미치는 영향**을 기준으로 분류하라.

판단 기준:
- 긍정: 해당 섹터 주가에 호재
- 부정: 해당 섹터 주가에 악재
- 중립: 영향이 불분명하거나 단순 사실 전달

주의:
- 어휘가 아니라 맥락으로 판단하라. 예를 들어 '원유 재고 감소'는 에너지 섹터에 호재다.
- 다른 섹터에 대한 호재/악재는 이 섹터 기준으로는 중립일 수 있다.
- reason 은 15자 이내 한국어로 간결하게.

{blocks}

모든 헤드라인에 대해 s(섹터 번호), i(헤드라인 번호), tone(긍정/부정/중립), reason 을
빠짐없이 JSON 배열로 반환하라."""

SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "s": {"type": "INTEGER"},
            "i": {"type": "INTEGER"},
            "tone": {"type": "STRING", "enum": ["긍정", "부정", "중립"]},
            "reason": {"type": "STRING"},
        },
        "required": ["s", "i", "tone", "reason"],
    },
}


def is_enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def model_name() -> str:
    return os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)


def _post(body: dict, key: str) -> tuple[dict | None, str | None]:
    """재시도 포함 단일 호출. (응답, 오류사유)"""
    req = urllib.request.Request(
        ENDPOINT.format(model=model_name()),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    last = "unknown"
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read()), None
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            # 429(분당 제한) / 5xx 는 기다렸다 재시도할 가치가 있다
            if e.code in (429, 500, 502, 503, 504) and attempt < RETRIES - 1:
                wait = e.headers.get("Retry-After")
                time.sleep(float(wait) if wait and wait.isdigit() else BACKOFF * (attempt + 1))
                continue
            return None, last
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = f"{type(e).__name__}"
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF * (attempt + 1))
                continue
            return None, last
        except ValueError as e:
            return None, f"parse: {type(e).__name__}"
    return None, last


def classify_chunk(group: list[tuple[str, list[str]]]) -> tuple[dict[int, list[dict]] | None, str | None]:
    """섹터 묶음을 한 번에 분류한다.

    group: [(섹터명, [헤드라인, ...]), ...]
    반환: ({섹터인덱스: [{"tone","reason"}, ...]}, None) 또는 (None, 오류사유)
    """
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None, "GEMINI_API_KEY 없음"

    blocks = []
    for si, (name, titles) in enumerate(group):
        lines = "\n".join(f"  i={ti}. {t}" for ti, t in enumerate(titles))
        blocks.append(f"[s={si}] 섹터: {name}\n{lines}")

    body = {
        "contents": [{"parts": [{"text": PROMPT.format(blocks="\n\n".join(blocks))}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
        },
    }

    payload, err = _post(body, key)
    if payload is None:
        return None, err
    try:
        parsed = json.loads(payload["candidates"][0]["content"]["parts"][0]["text"])
    except (KeyError, IndexError, ValueError, TypeError):
        return None, "응답 형식 오류"
    if not isinstance(parsed, list):
        return None, "응답이 배열이 아님"

    out = {si: [{"tone": "neutral", "reason": ""} for _ in titles]
           for si, (_, titles) in enumerate(group)}
    for item in parsed:
        try:
            s, i = int(item["s"]), int(item["i"])
            if s in out and 0 <= i < len(out[s]):
                out[s][i] = {
                    "tone": TONE_MAP.get(str(item.get("tone")), "neutral"),
                    "reason": str(item.get("reason", ""))[:40],
                }
        except (KeyError, TypeError, ValueError):
            continue
    return out, None


def classify_all(sectors: list[tuple[str, list[str]]]) -> tuple[dict[int, list[dict]], list[str]]:
    """전체 섹터를 CHUNK 개씩 묶어 분류한다.

    반환: ({전체인덱스: [{"tone","reason"}, ...]}, 오류메시지 목록)
    """
    results: dict[int, list[dict]] = {}
    errors: list[str] = []
    todo = [(gi, s) for gi, s in enumerate(sectors) if s[1]]  # 기사 있는 섹터만

    for start in range(0, len(todo), CHUNK):
        chunk = todo[start:start + CHUNK]
        got, err = classify_chunk([s for _, s in chunk])
        if got is None:
            names = ", ".join(s[0] for _, s in chunk)
            errors.append(f"{err} ({names})")
            continue
        for local, (gi, _) in enumerate(chunk):
            if local in got:
                results[gi] = got[local]
    return results, errors

# -*- coding: utf-8 -*-
"""증권사 종목 링크 생성.

URL 패턴이 바뀌면 여기만 고치면 된다. 화면 쪽(app.js)은 이 값을 그대로 쓴다.
- 네이버 모바일/PC 패턴은 검증됨.
- 토스 패턴 A{code} 검증됨 (구형 091160, 신형 0091P0 양쪽 정상 로드).
"""
from __future__ import annotations

NAVER_M = "https://m.stock.naver.com/domestic/stock/{code}/total"
NAVER_PC = "https://finance.naver.com/item/main.naver?code={code}"
TOSS = "https://tossinvest.com/stocks/A{code}"


def build_links(code: str) -> dict[str, str]:
    code = str(code).strip()
    return {
        "naver_m": NAVER_M.format(code=code),
        "naver_pc": NAVER_PC.format(code=code),
        "toss": TOSS.format(code=code),
    }

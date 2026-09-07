# -*- coding: utf-8 -*-
"""ETF 종목코드 검증.

6자리 코드를 설정에 박아두면 상장폐지·명칭변경 시 '조용히 틀린 가격'이 나온다.
매 실행마다 실물 상장목록과 대조하고, 어긋나면 리포트를 만들지 않고 실패시킨다.
"""
from __future__ import annotations

import re
import warnings

warnings.filterwarnings("ignore")


def _norm(s: str) -> str:
    """공백/특수문자 무시하고 비교하기 위한 정규화."""
    return re.sub(r"[\s\-_&()]+", "", str(s)).upper()


def load_listing() -> dict[str, str]:
    """FDR 상장 ETF 목록 -> {코드: 이름}"""
    import FinanceDataReader as fdr

    df = fdr.StockListing("ETF/KR")
    return {str(r.Symbol).strip(): str(r.Name).strip() for r in df.itertuples()}


def verify(etfs: list[dict], listing: dict[str, str] | None = None) -> tuple[list[dict], list[str]]:
    """설정의 ETF 목록을 검증한다.

    반환: (검증된 ETF 목록, 문제 메시지 목록)
    문제가 하나라도 있으면 호출부가 파이프라인을 중단시킨다.
    """
    if listing is None:
        listing = load_listing()

    ok, problems = [], []
    for e in etfs:
        code, want = str(e["code"]).strip(), str(e["name"]).strip()
        actual = listing.get(code)
        if actual is None:
            problems.append(f"[{code}] {want}: 상장목록에 없음 (상장폐지/코드변경 의심)")
            continue
        if _norm(actual) != _norm(want):
            problems.append(f"[{code}] 설정='{want}' 실제='{actual}' 명칭 불일치")
            continue
        ok.append({**e, "name": actual})
    return ok, problems

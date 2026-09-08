# -*- coding: utf-8 -*-
"""리포트 JSON 조립 및 출력."""
from __future__ import annotations

import json

import pandas as pd

from .momentum import LABEL, STRONG, TURNING
from .util import DOCS_DATA

SCHEMA_VERSION = 1
STALE_DAYS = 4


def freshness(kr_asof: pd.Timestamp, sources: dict[str, str], failed: list[str]) -> dict:
    """데이터 신선도. 캐시로 버틴 날은 화면에 경고 배너를 강제한다."""
    lag = (pd.Timestamp.today().normalize() - kr_asof.normalize()).days
    cached = [c for c, s in sources.items() if s == "cache"]
    if failed:
        status, msg = "failed", f"{len(failed)}개 종목 수집 실패: {', '.join(failed)}"
    elif cached:
        status, msg = "stale", f"{len(cached)}개 종목이 캐시 데이터입니다. 가격을 반드시 직접 확인하세요."
    elif lag > STALE_DAYS:
        status, msg = "stale", f"한국 시세가 {lag}일 전 데이터입니다."
    else:
        status, msg = "ok", ""
    return {
        "status": status,
        "message": msg,
        "kr_lag_days": int(lag),
        "cached_codes": cached,
        "failed_codes": failed,
    }


def make_headline(sectors: list[dict], picks: list[dict], regime: dict) -> str:
    if not sectors:
        return "미국 섹터 데이터를 가져오지 못했습니다."
    top = sectors[0]
    head = f"미국 시장에서 {top['name']}({top['ticker']}) 섹터가 20일 {top['r20']:+.1f}%로 가장 강했습니다."
    if not regime["risk_on"]:
        head += " 다만 S&P500이 200일선 아래라 약세 국면이므로 비중을 줄이세요."
    if picks:
        p = picks[0]
        head += (f" 연결 종목 중에서는 {p['name']} {p['entry']:,}원 지정가 예약을 우선 검토하세요"
                 f" ({p['setup_label']}).")
    else:
        head += " 오늘은 진입 조건을 만족하는 종목이 없어 전체 관망을 권합니다."
    return head


def build_report(*, report_date, us_asof, kr_asof, regime, sectors, picks, watch,
                 fresh, generated_at) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_date": str(report_date),
        "generated_at_kst": generated_at.isoformat(timespec="seconds"),
        "us_asof": str(us_asof),
        "kr_asof": str(kr_asof),
        "freshness": fresh,
        "market_regime": regime,
        "headline": make_headline(sectors, picks, regime),
        "us_sectors": sectors,
        "picks": picks,
        "watch": watch,
        "signal_labels": LABEL,
        "issue_disclaimer": (
            "섹터 이슈의 긍정/부정 표시는 헤드라인 키워드 자동 분류이며 문맥을 읽지 못합니다. "
            "읽을거리 우선순위 참고용이고, 매매 판단 근거로 쓰지 마세요."
        ),
        "counts": {"picks": len(picks), "watch": len(watch), "sectors": len(sectors)},
    }


def write_outputs(report: dict) -> list:
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    dated = DOCS_DATA / f"{report['report_date']}.json"
    latest = DOCS_DATA / "latest.json"

    for p in (dated, latest):
        p.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    # 아카이브 목록 갱신 (최신순)
    dates = sorted(
        (p.stem for p in DOCS_DATA.glob("20*.json")), reverse=True
    )
    (DOCS_DATA / "archive.json").write_text(
        json.dumps({"dates": dates}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return [dated, latest, DOCS_DATA / "archive.json"]

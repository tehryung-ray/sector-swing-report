# -*- coding: utf-8 -*-
"""매일 아침 섹터 스윙 리포트 생성 파이프라인.

실행: python -m pipeline.main
"""
from __future__ import annotations

import io
import json
import os
import sys

import yaml

from .gates import evaluate
from .levels import compute_levels
from .market_calendar import is_kr_session, next_kr_session
from .links import build_links
from . import news as news_mod
from .momentum import LABEL, WEAK, market_regime, rank_sectors
from .render import build_report, freshness, write_outputs
from .review import build_review, us_signal_frame
from .util import DOCS_DATA
from .resolve_codes import verify
from .sources.kr import fetch_kr
from .sources.us import fetch_us
from datetime import timedelta

from .util import CONFIG_DIR, now_kst

SIGNAL_ORDER = {"strong": 0, "turning": 1, "neutral": 2, "weak": 3}


def _load(name: str) -> dict:
    return yaml.safe_load(io.open(CONFIG_DIR / name, encoding="utf-8"))


def log(msg: str) -> None:
    print(msg, flush=True)


BACKFILL_DAYS = 365          # 복기 페이지의 백테스트 구간 길이


def load_past_reports() -> list[dict]:
    """보관된 일자별 리포트를 최신순으로 읽는다."""
    out = []
    for p in sorted(DOCS_DATA.glob("20*.json"), reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("report_date"):
                out.append(d)
        except (OSError, ValueError):
            continue
    return out


def already_done_today(today) -> bool:
    """2차 실행(재시도)에서 1차가 이미 성공했으면 중복 생성하지 않는다."""
    p = DOCS_DATA / "latest.json"
    if not p.exists():
        return False
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return d.get("report_date") == str(today) and d.get("freshness", {}).get("status") == "ok"


def main() -> int:
    generated_at = now_kst()
    today = generated_at.date()
    log(f"== 섹터 스윙 리포트 생성 {generated_at:%Y-%m-%d %H:%M:%S KST} ==")

    # --- 0. 조기 종료 조건 ---
    if os.environ.get("SKIP_IF_DONE") and already_done_today(today):
        log(f"   {today} 리포트가 이미 정상 생성되어 있습니다. 종료합니다.")
        return 0

    session = is_kr_session(today)
    if session is False and not os.environ.get("FORCE"):
        nxt = next_kr_session(today)
        log(f"   {today} 는 한국 증시 휴장일입니다. 다음 개장일: {nxt or '알 수 없음'}")
        log("   리포트를 만들지 않고 종료합니다 (강제 실행: FORCE=1)")
        return 0
    if session is None:
        log("   경고: 개장일 판정 불가 - 일단 생성을 진행합니다")

    us_cfg, kr_cfg = _load("us_sectors.yaml"), _load("kr_universe.yaml")

    # --- 1. 종목코드 검증 (틀리면 리포트를 만들지 않는다) ---
    log("[1/6] 종목코드 검증")
    etfs, problems = verify(kr_cfg["etfs"])
    if problems:
        log("!! 종목코드 검증 실패 - config/kr_universe.yaml 을 수정하세요:")
        for p in problems:
            log(f"   - {p}")
        return 1
    log(f"      {len(etfs)}종목 통과")

    # --- 2. 미국 섹터 ---
    log("[2/6] 미국 섹터 수집")
    bench = us_cfg["benchmark"]
    tickers = [s["ticker"] for s in us_cfg["sectors"]] + [bench]
    us = fetch_us(tickers)
    if bench not in us:
        log(f"!! 벤치마크 {bench} 수집 실패")
        return 1
    missing = sorted(set(tickers) - set(us))
    if missing:
        log(f"      경고: 미수집 {missing}")

    regime = market_regime(us[bench], us_cfg.get("regime_ma", 200))
    sectors = rank_sectors(us, us_cfg["sectors"], bench)
    sig_by_ticker = {s["ticker"]: s for s in sectors}
    us_asof = us[bench].index[-1].date()
    log(f"      {len(sectors)}섹터 / 국면 {regime['label']} / 기준일 {us_asof}")

    # --- 2-b. 섹터 이슈(뉴스) ---
    # 실패해도 리포트는 만든다. 뉴스는 참고 정보이지 매매 근거가 아니다.
    if os.environ.get("SKIP_NEWS"):
        log("      뉴스 수집 건너뜀 (SKIP_NEWS)")
        issues = {}
    else:
        log("      섹터 이슈 수집")
        try:
            issues, warns = news_mod.collect(us_cfg["sectors"], limit=5, days=3)
        except Exception as exc:
            log(f"      경고: 뉴스 수집 실패 ({type(exc).__name__}) - 이슈 없이 진행")
            issues, warns = {}, []
        got = sum(1 for v in issues.values() if v["summary"]["count"])
        ai = sum(1 for v in issues.values() if v["summary"]["classifier"].startswith("gemini"))
        log(f"      {got}/{len(us_cfg['sectors'])}개 섹터에서 이슈 확보 (AI 분류 {ai}개)")
        # 조용한 성능 저하를 막는다. 왜 사전 분류로 떨어졌는지 로그에 남긴다.
        for w in warns:
            log(f"      경고: Gemini 분류 실패 -> 키워드 폴백: {w}")
    for row in sectors:
        blk = issues.get(row["ticker"], {})
        row["issues"] = blk.get("items", [])
        row["issue_summary"] = blk.get("summary", news_mod.summarize([]))

    # --- 3. 한국 ETF ---
    log("[3/6] 한국 ETF 수집")
    codes = [e["code"] for e in etfs]
    kr, srcs, failed = fetch_kr(codes)
    if not kr:
        log("!! 한국 시세를 전혀 가져오지 못했습니다")
        return 1
    kr_asof = max(df.index[-1] for df in kr.values())
    by_src: dict[str, int] = {}
    for s in srcs.values():
        by_src[s] = by_src.get(s, 0) + 1
    log(f"      {len(kr)}/{len(codes)}종목 / 소스 {by_src} / 기준일 {kr_asof.date()}")

    # --- 4. 가격대 산출 + 관망 게이트 ---
    log("[4/6] 가격대 산출")
    picks, watch = [], []
    for e in etfs:
        code, df = e["code"], kr.get(e["code"])
        us_sec = sig_by_ticker.get(e["us"])
        if df is None or us_sec is None:
            watch.append({"code": code, "name": e["name"], "us_ticker": e["us"],
                          "reasons": ["시세 또는 매핑 섹터 데이터 없음"]})
            continue

        lv = compute_levels(df)
        if lv is None:
            watch.append({"code": code, "name": e["name"], "us_ticker": e["us"],
                          "reasons": ["시세 데이터 부족 (60일 미만)"]})
            continue

        row = {
            "code": code, "name": e["name"],
            "us_ticker": e["us"], "us_name": us_sec["name"],
            "us_r20": us_sec["r20"],
            "signal": us_sec["signal"], "signal_label": LABEL[us_sec["signal"]],
            "issue_summary": us_sec.get("issue_summary", {}),
            "issues": us_sec.get("issues", [])[:3],
            "source": srcs.get(code, "?"),
            **lv,
            "links": build_links(code),
        }
        reasons = evaluate(lv, us_sec["signal"])
        if reasons:
            row["reasons"] = reasons
            watch.append(row)
        else:
            picks.append(row)

    picks.sort(key=lambda r: (SIGNAL_ORDER.get(r["signal"], 9), -r["rr"]))
    watch.sort(key=lambda r: SIGNAL_ORDER.get(r.get("signal", "weak"), 9))
    log(f"      추천 {len(picks)}종목 / 관망 {len(watch)}종목")

    # --- 5. 출력 ---
    log("[5/6] JSON 출력")
    fresh = freshness(kr_asof, srcs, failed)
    if fresh["status"] != "ok":
        log(f"      경고[{fresh['status']}]: {fresh['message']}")

    report = build_report(
        report_date=generated_at.date(), us_asof=us_asof, kr_asof=kr_asof.date(),
        regime=regime, sectors=sectors, picks=picks, watch=watch,
        fresh=fresh, generated_at=generated_at,
    )
    for p in write_outputs(report):
        log(f"      -> {p.relative_to(p.parent.parent.parent)}")

    # --- 6. 복기 데이터 ---
    # 지난 추천이 실제로 어떻게 됐는지. 실패해도 오늘 리포트는 이미 나갔으므로 치명적이지 않다.
    log("[6/6] 복기 데이터")
    try:
        past = load_past_reports()
        sig = us_signal_frame(us, us_cfg["sectors"], bench)
        start = (generated_at.date() - timedelta(days=BACKFILL_DAYS)).isoformat()
        rev = build_review(past, kr, sig, etfs, generated_at, start)
        (DOCS_DATA / "review.json").write_text(
            json.dumps(rev, ensure_ascii=False, indent=1), encoding="utf-8")
        ls, bs = rev["live"]["stats"], rev["backtest"]["stats"]
        log(f"      실제 {ls.get('n',0)}건(체결 {ls.get('filled',0)}, 보유중 {ls.get('open',0)})"
            f" / 백테스트 {bs.get('n',0)}건")
        log(f"      대전제: 강한상승-하락세 {rev['premise']['strong_minus_weak']:+.3f}%p"
            f" ({'성립' if rev['premise']['holds'] else '불성립'})")
        log("      -> docs/data/review.json")
    except Exception as exc:
        log(f"      경고: 복기 생성 실패 ({type(exc).__name__}: {exc})")

    log("== 완료 ==")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""매일 아침 섹터 스윙 리포트 생성 파이프라인.

실행: python -m pipeline.main
"""
from __future__ import annotations

import io
import sys

import yaml

from .gates import evaluate
from .levels import compute_levels
from .links import build_links
from .momentum import LABEL, WEAK, market_regime, rank_sectors
from .render import build_report, freshness, write_outputs
from .resolve_codes import verify
from .sources.kr import fetch_kr
from .sources.us import fetch_us
from .util import CONFIG_DIR, now_kst

SIGNAL_ORDER = {"strong": 0, "turning": 1, "neutral": 2, "weak": 3}


def _load(name: str) -> dict:
    return yaml.safe_load(io.open(CONFIG_DIR / name, encoding="utf-8"))


def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    generated_at = now_kst()
    log(f"== 섹터 스윙 리포트 생성 {generated_at:%Y-%m-%d %H:%M:%S KST} ==")

    us_cfg, kr_cfg = _load("us_sectors.yaml"), _load("kr_universe.yaml")

    # --- 1. 종목코드 검증 (틀리면 리포트를 만들지 않는다) ---
    log("[1/5] 종목코드 검증")
    etfs, problems = verify(kr_cfg["etfs"])
    if problems:
        log("!! 종목코드 검증 실패 - config/kr_universe.yaml 을 수정하세요:")
        for p in problems:
            log(f"   - {p}")
        return 1
    log(f"      {len(etfs)}종목 통과")

    # --- 2. 미국 섹터 ---
    log("[2/5] 미국 섹터 수집")
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

    # --- 3. 한국 ETF ---
    log("[3/5] 한국 ETF 수집")
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
    log("[4/5] 가격대 산출")
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
    log("[5/5] JSON 출력")
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
    log("== 완료 ==")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

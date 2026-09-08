# -*- coding: utf-8 -*-
"""개장 점검 실행기. 09:10 에 돌린다.

실행: python -m pipeline.check_open
환경변수:
  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID  없으면 화면에만 출력한다
  DRY_RUN=1                              전송하지 않고 결과만 본다
"""
from __future__ import annotations

import json
import sys

from .market_calendar import is_kr_session
from .openbell import (CANCEL, FILLED, WAITING, build_message, fetch_today,
                       judge, send_telegram)
from .util import DOCS_DATA, now_kst


def log(m: str) -> None:
    print(m, flush=True)


TEST_MESSAGE = "\n".join([
    "[테스트] 개장 점검 알림 연결 확인",
    "",
    "이 메시지가 보이면 텔레그램 설정이 정상입니다.",
    "실제 알림은 KST 09:10에, 손 쓸 일이 있을 때만 옵니다.",
    "",
    "· 시가가 취소선 아래로 열림 → 예약주문 취소",
    "· 진입가에 닿아 체결됨 → 익절·손절 주문 걸기",
    "",
    "할 일이 없는 날은 아무것도 오지 않습니다.",
])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    import os

    now = now_kst()
    today = now.date()
    log(f"== 개장 점검 {now:%Y-%m-%d %H:%M KST} ==")

    # 연결 확인용. 시세·휴장 여부와 무관하게 한 통 보내본다.
    # 장 시작 전에는 판정할 시세가 없어 실제 경로로는 전송이 일어나지 않으므로,
    # 텔레그램 설정이 맞는지 확인하려면 이 모드가 필요하다.
    if os.environ.get("TEST_SEND"):
        log("[테스트] 연결 확인 메시지 전송")
        ok, err = send_telegram(TEST_MESSAGE)
        log("      전송 성공" if ok else f"      전송 실패: {err}")
        return 0 if ok else 1

    if is_kr_session(today) is False:
        log("   한국 증시 휴장일입니다. 종료합니다.")
        return 0

    p = DOCS_DATA / "latest.json"
    if not p.exists():
        log("!! latest.json 이 없습니다")
        return 1
    rep = json.loads(p.read_text(encoding="utf-8"))

    if rep.get("report_date") != str(today):
        log(f"   리포트 기준일이 {rep.get('report_date')} 로 오늘이 아닙니다. 종료합니다.")
        return 0

    picks = rep.get("picks", [])
    if not picks:
        log("   오늘 추천이 없어 점검할 주문이 없습니다.")
        return 0

    log(f"[1/3] 당일 시세 조회 ({len(picks)}종목)")
    bars = fetch_today([p["code"] for p in picks], today)
    log(f"      {len(bars)}/{len(picks)}종목 확보")

    log("[2/3] 판정")
    rows = [judge(p, bars.get(p["code"])) for p in picks]
    for r in rows:
        extra = ""
        if r["state"] == CANCEL:
            extra = f" (시가 {r['open']:,.0f} < 취소선 {r['cancel_below']:,.0f})"
        elif r["state"] == FILLED:
            extra = f" (체결 {r['fill']:,.0f}, 현재 {r['pnl_pct']:+.2f}%)"
        elif r["state"] == WAITING:
            extra = f" (저가 {r['low']:,.0f} > 진입 {r['entry']:,.0f})"
        log(f"      {r['name'][:22]:24s} {r['label']}{extra}")

    log("[3/3] 알림")
    # 09:05 이후면 시세가 있어야 정상이다. 그때 전부 실패면 그것도 알린다.
    market_open = (now.hour, now.minute) >= (9, 5)
    msg = build_message(rep, rows, market_open=market_open)
    if msg is None:
        log("      손 쓸 일이 없어 보내지 않습니다.")
        return 0

    log("      --- 보낼 내용 ---")
    for line in msg.split("\n"):
        log(f"      {line}")

    if os.environ.get("DRY_RUN"):
        log("      DRY_RUN 이라 전송하지 않았습니다.")
        return 0

    ok, err = send_telegram(msg)
    log("      전송 완료" if ok else f"      전송 실패: {err}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

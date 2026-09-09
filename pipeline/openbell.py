# -*- coding: utf-8 -*-
"""개장 직후 점검 - 오늘 예약한 주문을 어떻게 해야 하는가.

09:10 에 돌면서 오늘 리포트의 추천 종목이 어떻게 열렸는지 보고,
**사람이 손을 써야 하는 것만** 알린다.

| 상황 | 판정 | 해야 할 일 |
|---|---|---|
| 시가 < 취소선(손절가) | 셋업 무효 | 예약주문 취소 |
| 저가 <= 진입가 | 체결됐을 것 | 익절·손절 주문 걸기 |
| 진입가까지 안 내려옴 | 미체결 | 없음 |

체결 판정이 중요하다. 체결됐는데 손절 주문을 안 걸면 규칙 전체가 무너진다.

일봉으로 판정하므로 09:10 시점에는 '저가'가 아직 갱신 중이다.
그래서 미체결로 나왔더라도 장중에 내려와 체결될 수 있다. 문구로 그 점을 밝힌다.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

import pandas as pd

CANCEL, FILLED, WAITING, INVALID = "cancel", "filled", "waiting", "invalid"

LABEL = {
    CANCEL: "예약주문 취소",
    FILLED: "체결 (익절·손절 주문 필요)",
    WAITING: "미체결",
    INVALID: "시세 확인 불가",
}


def judge(pick: dict, bar: dict | None) -> dict:
    """오늘 일봉(진행 중) 한 줄로 종목 상태를 판정한다."""
    base = {"code": pick["code"], "name": pick["name"],
            "entry": pick["entry"], "stop": pick["stop"],
            "tp1": pick["tp1"], "tp2": pick["tp2"],
            "cancel_below": pick.get("cancel_below", pick["stop"])}
    if not bar:
        return {**base, "state": INVALID, "label": LABEL[INVALID]}

    o, h, l, c = bar["Open"], bar["High"], bar["Low"], bar["Close"]
    base |= {"open": o, "last": c, "low": l, "high": h}

    # 갭하락 취소가 먼저다. 취소 대상이면 체결 여부를 따질 필요가 없다.
    if o < base["cancel_below"]:
        return {**base, "state": CANCEL, "label": LABEL[CANCEL]}
    if l <= pick["entry"]:
        fill = min(pick["entry"], o)
        return {**base, "state": FILLED, "label": LABEL[FILLED],
                "fill": fill, "pnl_pct": round((c / fill - 1) * 100, 2)}
    return {**base, "state": WAITING, "label": LABEL[WAITING]}


def fetch_today(codes: list[str], date) -> dict[str, dict]:
    """당일 봉을 가져온다. 장중이면 진행 중인 값이 온다."""
    import FinanceDataReader as fdr

    d = pd.Timestamp(date).normalize()
    out = {}
    for c in codes:
        try:
            df = fdr.DataReader(c, (d - pd.Timedelta(days=7)).strftime("%Y-%m-%d"))
            df = df[df.index.normalize() == d]
            if not df.empty:
                r = df.iloc[-1]
                out[c] = {k: float(r[k]) for k in ("Open", "High", "Low", "Close")}
        except Exception:
            continue
    return out


def build_message(report: dict, rows: list[dict], market_open: bool = False) -> str | None:
    """손 쓸 일이 있을 때만 문자열을 만든다. 없으면 None.

    market_open 은 '지금은 시세가 있어야 하는 시간'이라는 뜻이다.
    그 시간에 전 종목 시세를 못 받았다면 점검 자체가 실패한 것이므로 알려야 한다.
    조용히 넘어가면 취소해야 할 주문을 놓친다.
    """
    cancel = [r for r in rows if r["state"] == CANCEL]
    filled = [r for r in rows if r["state"] == FILLED]
    invalid = [r for r in rows if r["state"] == INVALID]

    if market_open and rows and len(invalid) == len(rows):
        return "\n".join([
            f"[{report['report_date']}] 개장 점검 실패",
            "",
            f"{len(rows)}종목 전부 시세를 가져오지 못했습니다.",
            "자동 점검이 되지 않았으니 직접 확인하세요.",
            "각 종목의 시가가 취소선 아래면 예약주문을 취소해야 합니다.",
        ])
    if not cancel and not filled:
        return None

    won = lambda v: f"{int(v):,}원"
    L = [f"[{report['report_date']}] 개장 점검"]

    if cancel:
        L.append("")
        L.append(f"■ 예약주문 취소 {len(cancel)}건")
        L.append("  시가가 손절가 아래로 열렸습니다. 셋업이 이미 깨졌습니다.")
        for r in cancel:
            L.append(f"  · {r['name']}")
            L.append(f"    시가 {won(r['open'])} < 취소선 {won(r['cancel_below'])}")

    if filled:
        L.append("")
        L.append(f"■ 체결 {len(filled)}건 - 익절·손절 주문을 거세요")
        for r in filled:
            L.append(f"  · {r['name']}  (현재 {r['pnl_pct']:+.2f}%)")
            L.append(f"    체결 {won(r['fill'])} / 현재 {won(r['last'])}")
            L.append(f"    1차 {won(r['tp1'])} 절반 지정가매도")
            L.append(f"    2차 {won(r['tp2'])} 나머지 지정가매도")
            L.append(f"    손절 {won(r['stop'])} 전량 스탑로스(자동감시)")
        L.append("")
        L.append("  손절은 지정가 매도로 걸면 즉시 팔립니다. 반드시 스탑로스로 거세요.")

    if invalid:
        # 일부만 실패했어도 알려야 한다. 판정 못 한 종목은 직접 봐야 한다.
        L.append("")
        L.append(f"※ {len(invalid)}종목은 시세를 못 받아 판정하지 못했습니다: "
                 + ", ".join(r["name"] for r in invalid))
    L.append("")
    L.append("장중 시세라 미체결 종목도 이후 진입가까지 내려오면 체결될 수 있습니다.")
    return "\n".join(L)


def send_telegram(text: str) -> tuple[bool, str]:
    """텔레그램 전송. 토큰이 없으면 조용히 건너뛴다."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 없음"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": text, "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            body = json.loads(r.read())
        return bool(body.get("ok")), "" if body.get("ok") else str(body)[:200]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ---------- 중복 발송 방지 ----------
# 크론을 여러 번 걸면 같은 알림이 반복 발송된다.
# 다만 09:10 에 '취소 1건'이었다가 09:30 에 '체결'이 추가되는 것은 새 정보이므로
# 내용이 바뀌면 다시 보낸다. 체결·취소 판정은 하루 안에서 되돌아가지 않으므로
# (취소는 시가 기준 고정, 체결은 저가가 닿으면 유지) 내용은 단조 증가한다.

STATE_FILE = "openbell.json"


def _digest(rows: list[dict]) -> str:
    import hashlib
    key = "|".join(sorted(f"{r['code']}:{r['state']}" for r in rows
                          if r["state"] in (CANCEL, FILLED)))
    return hashlib.sha256(key.encode()).hexdigest()[:16] if key else ""


def load_state(path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def should_send(state: dict, today, rows: list[dict]) -> tuple[bool, str]:
    """(보낼지, 사유). 같은 날 같은 내용이면 보내지 않는다."""
    dg = _digest(rows)
    if not dg:
        return False, "알릴 내용 없음"
    if state.get("date") == str(today) and state.get("digest") == dg:
        return False, "같은 내용을 이미 보냈음"
    if state.get("date") == str(today):
        return True, "상황이 바뀌어 다시 보냄"
    return True, "오늘 첫 발송"


def save_state(path, today, rows: list[dict], sent: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "date": str(today), "digest": _digest(rows), "sent": sent,
        "states": {r["code"]: r["state"] for r in rows},
    }, ensure_ascii=False, indent=1), encoding="utf-8")

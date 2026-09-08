# -*- coding: utf-8 -*-
"""복기 - 지난 추천이 실제로 어떻게 됐는지 시세와 대조한다.

## 청산 규칙은 설명서와 같아야 한다
백테스트는 1차 익절에서 전량 청산하는 보수적 모델을 썼지만,
사용자에게는 "1차에서 절반, 2차에서 나머지"를 안내했다.
복기는 **사용자가 실제로 하는 대로** 추적해야 의미가 있으므로 분할 매도를 모델링한다.

## 하루 안에서의 판정 순서
같은 날 손절과 익절을 모두 스쳤을 때 어느 쪽이 먼저인지는 일봉으로 알 수 없다.
**손절을 먼저 본다.** 실제보다 나쁘게 나올 수 있지만, 좋게 나오는 것보다 낫다.
"""
from __future__ import annotations

import pandas as pd

MAX_HOLD = 5          # 거래일. 초과 시 종가 청산
HALF_AT_TP1 = 0.5     # 1차 익절에서 파는 비중

FILLED, NOT_FILLED, CANCELLED, WAITING = "filled", "not_filled", "cancelled", "waiting"
OPEN, TP2, TP1_TIME, STOPPED, TIMED = "open", "tp2", "tp1_time", "stopped", "timed"

STATUS_LABEL = {
    OPEN: "보유 중",
    TP2: "2차 익절까지 완료",
    TP1_TIME: "1차 익절 후 시간 청산",
    STOPPED: "손절",
    TIMED: "시간 청산",
}
FILL_LABEL = {
    FILLED: "체결",
    NOT_FILLED: "미체결 (진입가까지 안 내려옴)",
    CANCELLED: "주문 취소 (시가가 손절가 아래)",
    WAITING: "대기 중 (아직 장이 열리지 않음)",
}


def _after(df: pd.DataFrame, date) -> pd.DataFrame:
    """리포트 기준일 다음 거래일부터."""
    return df[df.index > pd.Timestamp(date)]


def track_pick(pick: dict, df: pd.DataFrame, report_date) -> dict:
    """추천 1건을 실제 시세와 대조.

    반환에는 체결 여부, 진행 상태, 실현/미실현 손익이 담긴다.
    """
    entry, stop, tp1, tp2 = pick["entry"], pick["stop"], pick["tp1"], pick["tp2"]
    fwd = _after(df, report_date)
    base = {
        "code": pick["code"], "name": pick["name"], "report_date": str(report_date),
        "setup_label": pick.get("setup_label"), "signal_label": pick.get("signal_label"),
        "us_ticker": pick.get("us_ticker"), "us_name": pick.get("us_name"),
        "entry": entry, "stop": stop, "tp1": tp1, "tp2": tp2,
        "links": pick.get("links", {}),
    }
    if fwd.empty:
        # 아직 결과를 물을 수 없는 추천이다. 체결률 분모에 넣으면 지표가 왜곡된다.
        return {**base, "fill": WAITING, "fill_label": FILL_LABEL[WAITING],
                "status": None, "ret_pct": None, "days": 0, "pending": True}

    d0 = fwd.iloc[0]
    # 1) 갭하락 취소 규칙 - 시가가 손절가 아래면 주문을 냈어도 취소한다
    if d0["Open"] < stop:
        return {**base, "fill": CANCELLED, "fill_label": FILL_LABEL[CANCELLED],
                "status": None, "ret_pct": None, "days": 0,
                "open_px": float(d0["Open"]), "pending": False}
    # 2) 지정가 매수 체결 여부
    if d0["Low"] > entry:
        return {**base, "fill": NOT_FILLED, "fill_label": FILL_LABEL[NOT_FILLED],
                "status": None, "ret_pct": None, "days": 0,
                "low_px": float(d0["Low"]), "pending": False}

    fill_px = min(entry, float(d0["Open"]))
    remain, realized, legs = 1.0, 0.0, []
    status, days, exit_date = OPEN, 0, None

    for i in range(min(MAX_HOLD, len(fwd))):
        bar = fwd.iloc[i]
        days = i + 1
        # 손절 우선 판정
        hit_stop = bar["Open"] <= stop or bar["Low"] <= stop
        if hit_stop:
            px = float(bar["Open"]) if bar["Open"] <= stop else stop
            realized += remain * (px / fill_px - 1)
            legs.append({"day": days, "what": "손절", "qty": round(remain, 2), "px": px})
            remain, status, exit_date = 0.0, STOPPED, fwd.index[i]
            break
        if remain > HALF_AT_TP1 and bar["High"] >= tp1:      # 1차 익절 (절반)
            realized += HALF_AT_TP1 * (tp1 / fill_px - 1)
            legs.append({"day": days, "what": "1차 익절", "qty": HALF_AT_TP1, "px": tp1})
            remain -= HALF_AT_TP1
        if remain > 0 and bar["High"] >= tp2:                # 2차 익절 (나머지)
            realized += remain * (tp2 / fill_px - 1)
            legs.append({"day": days, "what": "2차 익절", "qty": round(remain, 2), "px": tp2})
            remain, status, exit_date = 0.0, TP2, fwd.index[i]
            break

    last_px = float(fwd.iloc[min(days, len(fwd)) - 1]["Close"])
    if remain > 0:
        if days >= MAX_HOLD or len(fwd) <= days:
            if days >= MAX_HOLD:                              # 시간 청산
                realized += remain * (last_px / fill_px - 1)
                legs.append({"day": days, "what": "시간 청산", "qty": round(remain, 2), "px": last_px})
                status = TP1_TIME if len(legs) > 1 else TIMED
                exit_date = fwd.index[days - 1]
                remain = 0.0
            else:
                status = OPEN
        else:
            status = OPEN

    unreal = remain * (last_px / fill_px - 1)
    return {
        **base,
        "fill": FILLED, "fill_label": FILL_LABEL[FILLED],
        "fill_px": round(fill_px), "last_px": round(last_px),
        "status": status, "status_label": STATUS_LABEL[status],
        "ret_pct": round((realized + unreal) * 100, 2),
        "realized_pct": round(realized * 100, 2),
        "remain": round(remain, 2),
        "days": days, "legs": legs,
        "exit_date": str(exit_date.date()) if exit_date is not None else None,
        "pending": status == OPEN,
    }


# ============================================================
# 집계 · 대전제 검증 · 백필
# ============================================================

import numpy as np

from .gates import evaluate
from .levels import compute_levels
from .momentum import LABEL, NEUTRAL, STRONG, TURNING, WEAK


def summarize(trades: list[dict]) -> dict:
    """거래 목록 -> 요약 통계. 미체결도 분모에 넣어 체결률을 낸다."""
    if not trades:
        return {"n": 0}
    waiting = [t for t in trades if t["fill"] == WAITING]
    tested = [t for t in trades if t["fill"] != WAITING]      # 결과를 물을 수 있는 것만
    filled = [t for t in tested if t["fill"] == FILLED]
    closed = [t for t in filled if not t["pending"]]
    rets = np.array([t["ret_pct"] for t in closed]) if closed else np.array([])
    wins = rets > 0
    return {
        "n": len(trades),
        "waiting": len(waiting),
        "tested": len(tested),
        "filled": len(filled),
        "fill_rate": round(len(filled) / len(tested) * 100, 1) if tested else None,
        "cancelled": sum(1 for t in tested if t["fill"] == CANCELLED),
        "open": sum(1 for t in filled if t["pending"]),
        "closed": len(closed),
        "win_rate": round(float(wins.mean() * 100), 1) if len(rets) else None,
        "avg_ret": round(float(rets.mean()), 3) if len(rets) else None,
        "avg_win": round(float(rets[wins].mean()), 2) if wins.any() else None,
        "avg_loss": round(float(rets[~wins].mean()), 2) if (~wins).any() else None,
        "best": round(float(rets.max()), 2) if len(rets) else None,
        "worst": round(float(rets.min()), 2) if len(rets) else None,
        "stopped": sum(1 for t in closed if t["status"] == STOPPED),
    }


def us_signal_frame(us: dict[str, pd.DataFrame], sectors: list[dict], bench: str) -> pd.DataFrame:
    """날짜 x 티커 의 신호 등급 표. momentum.rank_sectors 와 같은 정의를 벡터화한 것."""
    close = pd.DataFrame({s["ticker"]: us[s["ticker"]]["Close"]
                          for s in sectors if s["ticker"] in us}).sort_index()
    if bench not in us:
        return pd.DataFrame()
    b20 = us[bench]["Close"].pct_change(20).reindex(close.index)

    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    r1, r5, r20 = close.pct_change(1), close.pct_change(5), close.pct_change(20)
    mom = 0.5 * r5 + 0.3 * r20 + 0.2 * r1
    rs = r20.sub(b20, axis=0)
    above = close > ma20
    trend_up = above & (ma20 > ma60)
    # 최근 5거래일 중 하루라도 20일선 아래였다가 지금 위 = 상향 돌파
    cross_up = above & ~above.shift(1).rolling(5).min().astype(bool)
    # 모멘텀 상위 30% (그날 유효한 섹터 기준)
    rank = mom.rank(axis=1, ascending=False)
    cnt = mom.notna().sum(axis=1)
    top = rank.le(np.ceil(cnt * 0.30), axis=0)

    sig = pd.DataFrame(NEUTRAL, index=close.index, columns=close.columns)
    sig = sig.mask(cross_up, TURNING)
    sig = sig.mask(top & (rs > 0) & trend_up, STRONG)
    sig = sig.mask(~above, WEAK)
    sig = sig.mask(close.isna() | ma60.isna(), None)
    return sig


def premise_stats(kr: dict[str, pd.DataFrame], sig: pd.DataFrame,
                  universe: list[dict], days: int = 3) -> dict:
    """대전제 검증 - 미국 섹터 신호별로 한국 연결 종목이 실제로 올랐는가.

    이 전략 전체가 '미국에서 강한 섹터가 다음날 한국으로 이어진다'는 가정 위에 있다.
    그 가정이 지금도 살아있는지 계속 감시하기 위한 통계다.
    """
    buckets: dict[str, list[float]] = {k: [] for k in (STRONG, TURNING, NEUTRAL, WEAK)}
    for e in universe:
        df, t = kr.get(e["code"]), e["us"]
        if df is None or t not in sig.columns:
            continue
        fwd = df["Close"].pct_change(days).shift(-days)      # 이후 days 거래일 수익률
        s = sig[t].reindex(df.index).ffill()
        for k in buckets:
            m = (s == k) & fwd.notna()
            if m.any():
                buckets[k].extend((fwd[m] * 100).tolist())

    out = []
    for k in (STRONG, TURNING, NEUTRAL, WEAK):
        v = np.array(buckets[k])
        if len(v) < 30:
            continue
        se = v.std(ddof=1) / np.sqrt(len(v))
        out.append({
            "signal": k, "label": LABEL[k], "n": len(v),
            "avg": round(float(v.mean()), 3),
            "win_rate": round(float((v > 0).mean() * 100), 1),
            "t": round(float(v.mean() / se), 2) if se > 0 else 0.0,
        })
    strong = next((x for x in out if x["signal"] == STRONG), None)
    weak = next((x for x in out if x["signal"] == WEAK), None)
    gap = round(strong["avg"] - weak["avg"], 3) if strong and weak else None
    return {"days": days, "by_signal": out, "strong_minus_weak": gap,
            "holds": bool(gap is not None and gap > 0)}


def backfill(kr: dict[str, pd.DataFrame], sig: pd.DataFrame, universe: list[dict],
             start: str, watch_days: int = 3) -> tuple[list[dict], dict]:
    """과거 구간을 같은 로직으로 재현한다.

    게이트가 미국 쪽에서 보는 것은 '하락세인가'뿐이고 하락세 = 종가 < 20일선 이므로,
    여기서 쓰는 신호는 프로덕션과 동일한 판정을 낸다.
    실제 추천 기록이 아니라 백테스트이며, 화면에서 반드시 구분해 표기한다.
    """
    start_ts = pd.Timestamp(start)
    out: list[dict] = []
    watch: dict[str, list[float]] = {}
    for e in universe:
        df, t = kr.get(e["code"]), e["us"]
        if df is None or len(df) < 80 or t not in sig.columns:
            continue
        s = sig[t].reindex(df.index).ffill()
        i, n = 60, len(df)
        while i < n - 1:
            d = df.index[i]
            if d < start_ts:
                i += 1; continue
            if pd.isna(s.iloc[i]):
                i += 1; continue
            lv = compute_levels(df.iloc[:i + 1])
            reasons = evaluate(lv, s.iloc[i]) if lv is not None else ["시세 부족"]
            if reasons:
                # 관망 판정. 안 산 것이 옳았는지 이후 수익률로 확인한다.
                if i + watch_days < n:
                    r = (df["Close"].iloc[i + watch_days] / df["Close"].iloc[i] - 1) * 100
                    key = reason_key(reasons[0])
                    watch.setdefault(key, []).append(float(r))
                i += 1; continue
            pick = {"code": e["code"], "name": e["name"], "entry": lv["entry"],
                    "stop": lv["stop"], "tp1": lv["tp1"], "tp2": lv["tp2"],
                    "setup_label": lv["setup_label"], "us_ticker": t,
                    "signal_label": LABEL.get(s.iloc[i], "")}
            r = track_pick(pick, df, d)
            r["source"] = "backtest"
            out.append(r)
            i += max(r.get("days", 1), 1) + 1
    out.sort(key=lambda x: x["report_date"])
    return out, watch


# 관망 사유 메시지에는 숫자가 섞여 있어(손익비 0.84 / 이격 +15.85% 과열) 그대로 묶으면
# 사유마다 표본이 1~2건으로 흩어진다. 안정적인 범주로 정규화한다.
# 순서 주의: '60일선' 을 먼저 봐야 '20일선 아래' 와 섞이지 않는다.
WATCH_CATEGORIES = [
    ("미국", "미국 섹터가 하락세"),
    ("60일선", "중기 추세 미회복"),
    ("20일선 아래", "국내 20일선 아래"),
    ("과열", "20일선 이격 과열"),
    ("손익비", "손익비 미달"),
    ("거래대금", "거래대금 부족"),
    ("1차 익절", "상승폭 부족"),
    ("손절가가", "가격 계산 이상"),
    ("시세", "시세 데이터 부족"),
]


def reason_key(msg: str) -> str:
    for k, label in WATCH_CATEGORIES:
        if k in msg:
            return label
    return "기타"


def watch_stats(reports: list[dict], kr: dict[str, pd.DataFrame], days: int = 3,
                extra: dict[str, list[float]] | None = None) -> dict:
    """관망 종목 점검 - 안 산 것이 옳았는가. 사유별 이후 수익률.

    extra 로 백테스트 구간의 관망 기록을 합칠 수 있다.
    실제 리포트가 쌓이기 전에도 사유별 경향을 볼 수 있게 하기 위함이다.
    """
    by: dict[str, list[float]] = {k: list(v) for k, v in (extra or {}).items()}
    for rep in reports:
        d = pd.Timestamp(rep["report_date"])
        for w in rep.get("watch", []):
            df = kr.get(w["code"])
            if df is None:
                continue
            fwd = df[df.index > d]
            if len(fwd) <= days:
                continue
            base = df[df.index <= d]
            if base.empty:
                continue
            ret = (fwd.iloc[days - 1]["Close"] / base.iloc[-1]["Close"] - 1) * 100
            key = reason_key((w.get("reasons") or ["기타"])[0])
            by.setdefault(key, []).append(float(ret))
    out = []
    for k, v in sorted(by.items(), key=lambda x: -len(x[1])):
        a = np.array(v)
        out.append({"reason": k, "n": len(a), "avg": round(float(a.mean()), 2),
                    "up_rate": round(float((a > 0).mean() * 100), 1)})
    return {"days": days, "by_reason": out}


def build_review(reports: list[dict], kr: dict[str, pd.DataFrame], sig: pd.DataFrame,
                 universe: list[dict], generated_at, backfill_start: str) -> dict:
    """복기 데이터 조립. 실제 기록과 백테스트를 분리해 담는다."""
    live = []
    for rep in reports:
        for p in rep.get("picks", []):
            df = kr.get(p["code"])
            if df is None:
                continue
            r = track_pick(p, df, rep["report_date"])
            r["source"] = "live"
            live.append(r)
    live.sort(key=lambda x: x["report_date"], reverse=True)

    bt, bt_watch = backfill(kr, sig, universe, backfill_start)
    return {
        "schema_version": 1,
        "generated_at_kst": generated_at.isoformat(timespec="seconds"),
        "live": {"trades": live, "stats": summarize(live),
                 # 보유 중 = 체결됐고 아직 청산 안 된 것. 대기 중(장 미개장)은 제외한다.
                 "open": [t for t in live if t["fill"] == FILLED and t.get("pending")],
                 "waiting": [t for t in live if t["fill"] == WAITING],
                 "reports": len(reports),
                 "since": reports[-1]["report_date"] if reports else None},
        "backtest": {"trades": bt[-400:], "stats": summarize(bt),
                     "since": backfill_start,
                     "note": "실제 추천 기록이 아니라 같은 로직으로 과거를 재현한 결과입니다."},
        "premise": premise_stats(kr, sig, universe),
        "watch": watch_stats(reports, kr, extra=bt_watch),
        "rules": {"max_hold": MAX_HOLD, "half_at_tp1": HALF_AT_TP1},
    }

# -*- coding: utf-8 -*-
"""2차 익절을 고정 지정가 대신 트레일링(고점 대비 하락폭)으로 바꾸면 나아지는가.

## 비교 대상
- fixed : 1차에서 절반 익절, 나머지는 2차 익절가에 지정가 매도 (현행 안내)
- trail : 1차에서 절반 익절, 나머지는 2차 익절가를 넘어서면 감시 시작.
          이후 고점 대비 d% 하락하면 청산 (한투 자동감시주문 형태)

## 일봉으로 모델링할 때의 주의
같은 날 손절과 익절을 모두 스쳤을 때 순서를 알 수 없다. **손절을 먼저** 본다.
감시가 걸린 날에도 고점을 찍고 되밀렸을 수 있으므로 당일 트리거를 허용한다.
둘 다 실제보다 나쁘게 나오는 쪽이고, 좋게 나오는 것보다 낫다.
"""
from __future__ import annotations

import os
import sys
import warnings

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)

import numpy as np

import fast as F
from engine import DEFAULT

HALF = 0.5


def _tick(x, up=False):
    t = 1.0 if x < 2000 else 5.0
    return (np.ceil(x / t) if up else np.floor(x / t)) * t


def levels_at(a, i, p):
    """fast.run_fast 와 동일한 가격대 산출. 진입 조건을 만족하면 (e, s, t1, t2)."""
    cl, ma20, ma60, sd20 = a["close"], a["ma20"], a["ma60"], a["sd20"]
    low5, swing, hi10, hi60, atr = a["low5"], a["swing"], a["hi10"], a["hi60"], a["atr"]
    last, m20, m60, at = cl[i], ma20[i], ma60[i], atr[i]
    if not (at > 0) or not np.isfinite(m60) or not np.isfinite(sd20[i]) \
       or not np.isfinite(hi60[i]) or last <= m20:
        return None
    ext = (last - m20) / m20
    if ext > p["extended_max"]:
        return None
    if not (m20 > m60 or (np.isfinite(a["ma20_5"][i]) and m20 > a["ma20_5"][i])):
        return None
    if ext <= p["pullback_max"]:
        entry = max(m20, low5[i])
        tp1 = max(hi10[i], entry * (1 + p["min_tp1"]))
        bb = m20 + 2 * sd20[i]
        tp2 = min(bb, hi60[i])
        if tp2 <= tp1:
            tp2 = max(bb, hi60[i], tp1 * 1.04)
        stop = min(swing[i] * 0.99, entry * (1 - p["pb_min_loss"]))
        stop = max(stop, entry * (1 - p["pb_max_loss"]))
    else:
        entry = max(low5[i], last - p["dip_atr"] * at)
        stop = max(min(entry - at, entry * (1 - p["sh_min_loss"])),
                   entry * (1 - p["sh_max_loss"]))
        risk = entry - stop
        tp1 = entry + max(p["tp1_atr"] * at, p["tp1_risk"] * risk)
        tp2 = entry + max(p["tp2_atr"] * at, p["tp2_risk"] * risk)
    entry = min(entry, last)
    e, s = _tick(entry), _tick(stop, True)
    t1, t2 = _tick(tp1), _tick(tp2)
    if s >= e or t1 <= e or t2 <= t1:
        return None
    if (t1 - e) / (e - s) < p["min_rr"] or (t1 / e - 1) * 100 < p["min_upside"] \
       or a["turn"][i] < p["min_turnover"]:
        return None
    return e, s, t1, t2


def sim(p, mode="fixed", trail=0.03, y0=None, y1=None, max_hold=5, trail_hold=None,
        atr_mult=None):
    """atr_mult 를 주면 고점 대비 하락폭을 종목별 ATR 배수로 잡는다.
    ETF 마다 일간 변동성이 3~5%로 달라, 고정 %는 어떤 종목엔 넓고 어떤 종목엔 좁다."""
    """반환: (거래별 수익률 배열, 보유일 배열, 2차 청산가/2차익절가 비율 배열)"""
    trail_hold = trail_hold or max_hold
    R, H, X = [], [], []
    for code in F.A:
        a = F.A[code]; n = len(a["close"])
        cl, op, hi, lo = a["close"], a["open"], a["high"], a["low"]
        usok, yr = a["usok"], a["year"]
        i = 60
        while i < n - 1:
            if (y0 and yr[i] < y0) or (y1 and yr[i] > y1): i += 1; continue
            if p["us_filter"] and not usok[i]: i += 1; continue
            lv = levels_at(a, i, p)
            if lv is None: i += 1; continue
            e, s, t1, t2 = lv
            atr_i = a["atr"][i]
            if op[i + 1] < s or lo[i + 1] > e: i += 1; continue
            fill = min(e, op[i + 1])

            remain, realized, held = 1.0, 0.0, 0
            armed, peak, exit_ratio = False, 0.0, None
            cap = trail_hold if mode == "trail" else max_hold
            for k in range(i + 1, min(i + 1 + cap, n)):
                held = k - i
                # 1) 손절 우선
                if op[k] <= s or lo[k] <= s:
                    px = op[k] if op[k] <= s else s
                    realized += remain * (px / fill - 1); remain = 0.0; break
                # 2) 1차 익절 (절반)
                if remain > HALF and hi[k] >= t1:
                    realized += HALF * (t1 / fill - 1); remain -= HALF
                # 3) 나머지 절반
                if remain > 0:
                    if mode == "fixed":
                        if hi[k] >= t2:
                            realized += remain * (t2 / fill - 1); remain = 0.0
                            exit_ratio = 1.0; break
                    else:
                        if not armed and hi[k] >= t2:
                            armed, peak = True, hi[k]
                        if armed:
                            peak = max(peak, hi[k])
                            band = atr_mult * atr_i if atr_mult else peak * trail
                            trig = peak - band
                            if op[k] <= trig:
                                realized += remain * (op[k] / fill - 1)
                                exit_ratio = op[k] / t2; remain = 0.0; break
                            if lo[k] <= trig:
                                realized += remain * (trig / fill - 1)
                                exit_ratio = trig / t2; remain = 0.0; break
                # 보유기간 상한: 감시가 걸리지 않았으면 기본 상한을 적용한다
                if remain > 0 and not armed and held >= max_hold:
                    realized += remain * (cl[k] / fill - 1); remain = 0.0; break
            if remain > 0:
                k = min(i + held, n - 1)
                realized += remain * (cl[k] / fill - 1)
            R.append(realized); H.append(held)
            if exit_ratio is not None: X.append(exit_ratio)
            i = i + 1 + max(held, 1)
    return np.array(R), np.array(H), np.array(X)


def stat(R, H, lab):
    se = R.std(ddof=1) / np.sqrt(len(R)); eq = np.cumprod(1 + R); w = R > 0
    return dict(lab=lab, n=len(R), win=w.mean() * 100, m=R.mean() * 100,
                t=R.mean() / se, held=H.mean(),
                mdd=float((1 - eq / np.maximum.accumulate(eq)).max() * 100),
                cum=(eq[-1] - 1) * 100)


HDR = f"{'방식':22s}{'거래':>7}{'승률':>8}{'평균':>10}{'t':>7}{'MDD':>8}{'보유':>7}{'누적':>10}"


def show(s, base=None):
    d = "" if base is None else f"  ({s['m'] - base['m']:+.3f}%p)"
    print(f"{s['lab']:22s}{s['n']:>7d}{s['win']:>7.1f}%{s['m']:>+9.3f}%{s['t']:>+7.2f}"
          f"{s['mdd']:>7.1f}%{s['held']:>7.1f}{s['cum']:>+9.0f}%{d}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    P = DEFAULT
    print("=" * 104)
    print("2차 익절: 고정 지정가 vs 트레일링 (고점 대비 하락폭)   [검증구간 2021~2026]")
    print("=" * 104)
    print(HDR)
    Rb, Hb, Xb = sim(P, "fixed", y0=2021, y1=2026)
    base = stat(Rb, Hb, "고정 지정가 (현행)")
    show(base)
    print()
    for d in (0.02, 0.03, 0.04, 0.05, 0.07):
        R, H, X = sim(P, "trail", d, y0=2021, y1=2026)
        show(stat(R, H, f"트레일링 {d*100:.0f}% (5일 상한)"), base)
    print()
    print("감시가 걸리면 보유기간 상한을 늘렸을 때 (추세를 끝까지 따라감)")
    for d in (0.03, 0.05, 0.07):
        for th in (10, 20):
            R, H, X = sim(P, "trail", d, y0=2021, y1=2026, trail_hold=th)
            show(stat(R, H, f"트레일링 {d*100:.0f}% (상한 {th}일)"), base)

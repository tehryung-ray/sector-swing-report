# -*- coding: utf-8 -*-
"""포트폴리오 시뮬레이션 - 총자금을 몇 종목으로 나눌 것인가.

핵심 제약은 두 가지가 동시에 걸린다.
  1) 자금 제약 : 포지션 금액 = 위험금액 / 손절률. 손절이 좁을수록 매수금액이 커진다.
  2) 신호 제약 : 하루에 조건을 만족하는 종목이 몇 개 안 나온다. 슬롯이 남아도 채울 수 없다.
"""
import sys, os, warnings, pickle
warnings.filterwarnings("ignore"); sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from engine import DEFAULT
import fast as F

CAP0 = 30_000_000


def collect_trades(p, y0=2021, y1=2026):
    """거래를 (진입일, 청산일, 수익률, 손절률) 로 수집."""
    out = []
    for code in F.A:
        a = F.A[code]; n = len(a["close"])
        cl, op, hi, lo = a["close"], a["open"], a["high"], a["low"]
        ma20, ma60, sd20 = a["ma20"], a["ma60"], a["sd20"]
        low5, swing, hi10, hi60 = a["low5"], a["swing"], a["hi10"], a["hi60"]
        atr, turn, ma5, usok, yr = a["atr"], a["turn"], a["ma20_5"], a["usok"], a["year"]
        dates = F.KR[code]["df"].index
        mh = p["max_hold"]; i = 60
        while i < n - 1:
            if yr[i] < y0 or yr[i] > y1: i += 1; continue
            if p["us_filter"] and not usok[i]: i += 1; continue
            last, m20, m60, at = cl[i], ma20[i], ma60[i], atr[i]
            if not (at > 0) or not np.isfinite(m60) or not np.isfinite(sd20[i]) \
               or not np.isfinite(hi60[i]) or last <= m20: i += 1; continue
            ext = (last - m20) / m20
            if ext > p["extended_max"]: i += 1; continue
            if not (m20 > m60 or (np.isfinite(ma5[i]) and m20 > ma5[i])): i += 1; continue
            if ext <= p["pullback_max"]:
                entry = max(m20, low5[i]); bb = m20 + 2*sd20[i]
                tp1 = max(hi10[i], entry*(1+p["min_tp1"]))
                stop = max(min(min(swing[i]*0.99, entry*(1-p["pb_min_loss"])),
                               entry*(1-p["pb_min_loss"])), entry*(1-p["pb_max_loss"]))
            else:
                entry = max(low5[i], last - p["dip_atr"]*at)
                stop = max(min(entry-at, entry*(1-p["sh_min_loss"])), entry*(1-p["sh_max_loss"]))
                tp1 = entry + max(p["tp1_atr"]*at, p["tp1_risk"]*(entry-stop))
            entry = min(entry, last)
            e = np.floor(entry/(1 if entry < 2000 else 5))*(1 if entry < 2000 else 5)
            s = np.ceil(stop/(1 if stop < 2000 else 5))*(1 if stop < 2000 else 5)
            t1 = np.floor(tp1/(1 if tp1 < 2000 else 5))*(1 if tp1 < 2000 else 5)
            if s >= e or t1 <= e: i += 1; continue
            if (t1-e)/(e-s) < p["min_rr"] or (t1/e-1)*100 < p["min_upside"] \
               or turn[i] < p["min_turnover"]: i += 1; continue
            if op[i+1] < s or lo[i+1] > e: i += 1; continue
            fill = min(e, op[i+1]); px = None; held = 0
            for k in range(i+2, min(i+2+mh, n)):
                held = k-i-1
                if op[k] <= s: px = op[k]; break
                if lo[k] <= s: px = s; break
                if hi[k] >= t1: px = t1; break
            if px is None:
                k = min(i+1+mh, n-1); px, held = cl[k], k-i-1
            out.append({"code": code, "in": dates[i+1], "out": dates[min(i+1+held, n-1)],
                        "ret": (px/fill-1) - p["cost"], "stop_pct": (fill-s)/fill})
            i = i + 1 + max(held, 1)
    return pd.DataFrame(out).sort_values("in").reset_index(drop=True)


def simulate(tr, max_n, risk_pct, cap0=CAP0, max_weight=0.34):
    """슬롯 max_n 개, 거래당 위험 risk_pct(자산 대비).

    cash  = 미투자 현금
    equity = cash + 보유 포지션 원가 (실현 기준. 평가손익은 반영하지 않는 보수적 계산)
    """
    cash = float(cap0)
    open_pos = []                      # [exit_date, size, ret]
    curve = [cap0]
    taken = skip_slot = skip_cash = 0
    weights, idle = [], []

    def flush(upto):
        nonlocal cash
        open_pos.sort(key=lambda x: x[0])
        while open_pos and open_pos[0][0] <= upto:
            _, size, ret = open_pos.pop(0)
            cash += size * (1 + ret)
            curve.append(cash + sum(x[1] for x in open_pos))

    for _, t in tr.iterrows():
        flush(t["in"])
        equity = cash + sum(x[1] for x in open_pos)
        idle.append(len(open_pos))
        if len(open_pos) >= max_n:
            skip_slot += 1; continue
        size = equity * risk_pct / t["stop_pct"]       # 위험 기준 금액
        size = min(size, equity * max_weight, cash)    # 비중 상한 + 현금 한도
        if size < equity * 0.02:
            skip_cash += 1; continue
        cash -= size
        open_pos.append([t["out"], size, t["ret"]])
        weights.append(size / equity)
        taken += 1

    flush(pd.Timestamp("2099-01-01"))
    eq = np.array(curve)
    mdd = float((1 - eq / np.maximum.accumulate(eq)).max() * 100)
    return {"max_n": max_n, "risk": risk_pct*100, "final": cash,
            "ret": (cash/cap0 - 1)*100, "mdd": mdd,
            "taken": taken, "skip_slot": skip_slot, "skip_cash": skip_cash,
            "avg_w": np.mean(weights)*100 if weights else 0,
            "avg_open": np.mean(idle) if idle else 0}


if __name__ == "__main__":
    tr = collect_trades(DEFAULT)
    print(f"검증구간 2021~2026 총 거래 후보 {len(tr)}건\n")

    print("="*92); print("A. 신호 공급량 - 슬롯이 있어도 채울 종목이 있는가"); print("="*92)
    # 동시에 열려 있는 포지션 수의 분포 (슬롯 무제한 가정)
    ev = []
    for _, t in tr.iterrows():
        ev.append((t["in"], 1)); ev.append((t["out"], -1))
    ev.sort()
    cur = 0; series = []
    for d, x in ev:
        cur += x; series.append(cur)
    series = np.array(series)
    print(f"슬롯 무제한일 때 동시보유 종목 수: 평균 {series.mean():.1f}개, 중앙값 {np.median(series):.0f}개, 최대 {series.max()}개")
    for k in (1,2,3,4,5,6,8,10):
        print(f"  {k:2d}개 이상 동시보유한 시간 비중: {(series>=k).mean()*100:5.1f}%")

    print()
    print("="*92); print("B. 분할 개수별 성과 (총 3,000만원, 2021~2026)"); print("="*92)
    print(f"{'분할':>4}{'위험/거래':>10}{'평균비중':>9}{'최종자산':>13}{'수익률':>9}{'MDD':>8}"
          f"{'체결':>7}{'슬롯부족':>9}{'현금부족':>9}{'평균보유':>9}")
    for risk in (0.005, 0.0075, 0.010):
        for n in (2, 3, 4, 5, 6, 8):
            r = simulate(tr, n, risk)
            print(f"{n:>4}{r['risk']:>9.2f}%{r['avg_w']:>8.1f}%{r['final']/1e4:>11,.0f}만"
                  f"{r['ret']:>+8.1f}%{r['mdd']:>7.1f}%{r['taken']:>7d}{r['skip_slot']:>9d}"
                  f"{r['skip_cash']:>9d}{r['avg_open']:>9.1f}")
        print()

    print("="*92); print("C. 위험조정 성과 요약 (연환산)"); print("="*92)
    yrs = (tr["out"].max() - tr["in"].min()).days / 365.25
    print(f"기간 {tr['in'].min().date()} ~ {tr['out'].max().date()} ({yrs:.1f}년)")
    print(f"{'분할':>4}{'위험':>8}{'연환산':>9}{'MDD':>8}{'수익/MDD':>10}{'실제 평균보유':>13}{'슬롯낭비':>10}")
    best = []
    for risk in (0.005, 0.0075, 0.010):
        for n in (2, 3, 4, 5, 6, 8):
            r = simulate(tr, n, risk)
            cagr = ((1 + r["ret"]/100) ** (1/yrs) - 1) * 100
            ratio = cagr / r["mdd"] if r["mdd"] > 0 else 0
            waste = (1 - r["avg_open"]/n) * 100
            best.append((ratio, n, risk, cagr, r["mdd"], r["avg_open"], waste))
            print(f"{n:>4}{risk*100:>7.2f}%{cagr:>+8.1f}%{r['mdd']:>7.1f}%{ratio:>10.2f}"
                  f"{r['avg_open']:>12.1f}개{waste:>9.0f}%")
        print()
    best.sort(reverse=True)
    print("수익/MDD 상위 5:")
    for ratio, n, risk, cagr, mdd, avg, w in best[:5]:
        print(f"  {n}분할 · 위험 {risk*100:.2f}% → 연 {cagr:+.1f}% / MDD {mdd:.1f}% = {ratio:.2f}")

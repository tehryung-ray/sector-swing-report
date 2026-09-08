# -*- coding: utf-8 -*-
"""같은 미국 섹터에서 몇 종목까지 담을 것인가.

같은 섹터에 묶인 국내 ETF는 상관이 0.94~0.99 로 사실상 같은 종목이다
(TIGER 반도체TOP10 x KODEX 반도체 = 0.976).
제한 없이 담으면 분산이 아니라 한 종목을 두 배로 산 것이 된다.
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import fast as F
from engine import DEFAULT
from trail import levels_at


def collect(p, y0=2021, y1=2026):
    """진입일·섹터·수익률을 모아 온다."""
    out = []
    for code in F.A:
        a = F.A[code]; n = len(a["close"])
        cl, op, hi, lo = a["close"], a["open"], a["high"], a["low"]
        usok, yr = a["usok"], a["year"]
        dates = F.KR[code]["df"].index
        sec = F.KR[code]["us"]
        i, mh = 60, p["max_hold"]
        while i < n - 1:
            if yr[i] < y0 or yr[i] > y1: i += 1; continue
            if p["us_filter"] and not usok[i]: i += 1; continue
            lv = levels_at(a, i, p)
            if lv is None: i += 1; continue
            e, s, t1, _ = lv
            if op[i+1] < s or lo[i+1] > e: i += 1; continue
            fill = min(e, op[i+1]); px = None; held = 0
            for k in range(i+2, min(i+2+mh, n)):
                held = k-i-1
                if op[k] <= s: px = op[k]; break
                if lo[k] <= s: px = s; break
                if hi[k] >= t1: px = t1; break
            if px is None:
                k = min(i+1+mh, n-1); px, held = cl[k], k-i-1
            out.append({"date": dates[i+1], "code": code, "sector": sec,
                        "out": dates[min(i+1+held, n-1)],
                        "ret": (px/fill-1) - p["cost"]})
            i = i + 1 + max(held, 1)
    return pd.DataFrame(out).sort_values("date").reset_index(drop=True)


def sim(tr, max_n, per_sector, risk=0.005, cap0=30_000_000, max_w=0.34):
    """per_sector: 같은 미국 섹터에서 동시에 보유할 수 있는 최대 종목 수."""
    cash = float(cap0); open_pos = []; curve = [cap0]
    taken = skip_sec = skip_slot = 0

    def flush(upto):
        nonlocal cash
        open_pos.sort(key=lambda x: x[0])
        while open_pos and open_pos[0][0] <= upto:
            _, size, ret, _ = open_pos.pop(0)
            cash += size * (1 + ret)
            curve.append(cash + sum(x[1] for x in open_pos))

    for _, t in tr.iterrows():
        flush(t["date"])
        eq = cash + sum(x[1] for x in open_pos)
        if sum(1 for x in open_pos if x[3] == t["sector"]) >= per_sector:
            skip_sec += 1; continue
        if len(open_pos) >= max_n:
            skip_slot += 1; continue
        size = min(eq * risk / 0.03, eq * max_w, cash)
        if size < eq * 0.02: continue
        cash -= size
        open_pos.append([t["out"], size, t["ret"], t["sector"]])
        taken += 1
    flush(pd.Timestamp("2099-01-01"))
    e = np.array(curve)
    return {"n": taken, "skip_sec": skip_sec, "final": cash,
            "ret": (cash/cap0-1)*100,
            "mdd": float((1-e/np.maximum.accumulate(e)).max()*100)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    tr = collect(DEFAULT)
    print(f"거래 후보 {len(tr)}건\n")

    print("="*80); print("A. 같은 섹터가 같은 날 동시에 나오는 빈도"); print("="*80)
    g = tr.groupby(["date", "sector"]).size()
    dup = g[g > 1]
    days = tr["date"].nunique()
    print(f"  신호가 난 날 {days}일 중 같은 섹터 중복이 있는 날: {dup.index.get_level_values(0).nunique()}일"
          f" ({dup.index.get_level_values(0).nunique()/days*100:.0f}%)")
    print(f"  중복 발생 시 평균 {dup.mean():.1f}종목, 최대 {dup.max()}종목")
    print()
    print("  섹터별 중복 발생 횟수:")
    for s, c in dup.groupby(level=1).size().sort_values(ascending=False).items():
        print(f"    {s:5s} {c:4d}회")

    print()
    print("="*80); print("B. 섹터당 보유 제한별 성과 (3,000만원, 슬롯 5, 위험 0.5%)"); print("="*80)
    print(f"{'섹터당 제한':>10}{'체결':>7}{'섹터탈락':>9}{'최종자산':>13}{'수익률':>9}{'MDD':>8}")
    for ps in (1, 2, 3, 99):
        r = sim(tr, max_n=5, per_sector=ps)
        tag = "제한없음" if ps > 5 else f"{ps}종목"
        print(f"{tag:>10}{r['n']:>7}{r['skip_sec']:>9}{r['final']/1e4:>11,.0f}만{r['ret']:>+8.1f}%{r['mdd']:>7.1f}%")

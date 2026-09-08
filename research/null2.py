# -*- coding: utf-8 -*-
"""엄밀한 귀무모형: 주문·손절·익절 장치를 전부 동일하게 두고 '진입일 선택'만 무작위화."""
import sys, os, warnings; warnings.filterwarnings("ignore"); sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")); sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
from fast import run_fast
from engine import DEFAULT
from pipeline.util import round_tick

P = DEFAULT

def raw_levels(r):
    """게이트·추세필터 없이 항상 가격대를 산출한다 (귀무모형용)."""
    last, ma20, atr = r["close"], r["ma20"], r["atr"]
    if not np.isfinite([last, ma20, atr, r["low5"], r["hi10"]]).all() or atr <= 0:
        return None
    entry = min(max(r["low5"], last - P["dip_atr"]*atr), last)
    stop = max(entry - atr, entry*(1-P["sh_max_loss"]))
    stop = min(stop, entry*(1-P["sh_min_loss"]))
    risk = entry - stop
    tp1 = entry + max(P["tp1_atr"]*atr, P["tp1_risk"]*risk)
    e, s, t = round_tick(entry,"down"), round_tick(stop,"up"), round_tick(tp1,"down")
    return None if (s >= e or t <= e) else (e, s, t)


def simulate(code, day_idx):
    """주어진 진입 신호일들에 대해 실제와 동일한 주문·청산 규칙을 적용."""
    df = KR[code]["df"]; ind = _IND[code]
    o,h,l,c = (df[x].values for x in ("Open","High","Low","Close")); n = len(df)
    out = []
    for i in day_idx:
        if i >= n-1: continue
        lv = raw_levels(ind.iloc[i])
        if lv is None: continue
        e, s, t = lv
        if o[i+1] < s or l[i+1] > e: continue
        fill = min(e, o[i+1]); px = None; held = 0
        for hh in range(1, P["max_hold"]+1):
            k = i+1+hh
            if k >= n: break
            held = hh
            if o[k] <= s: px = o[k]; break
            if l[k] <= s: px = s; break
            if h[k] >= t: px = t; break
        if px is None:
            k = min(i+1+P["max_hold"], n-1); px, held = c[k], k-(i+1)
        out.append((px/fill - 1) - P["cost"])
    return out


real = run()
per = real.groupby("code").size().to_dict()
m_real = real["ret"].mean()*100

print("="*104)
print("엄밀한 귀무모형 - 지정가주문·손절·익절 전부 동일, 진입일 선택만 무작위")
print("="*104)
sims = []
for k in range(40):
    g = np.random.default_rng(500+k); rr = []
    for code, cnt in per.items():
        n = len(KR[code]["df"])
        if n < 80: continue
        rr += simulate(code, g.integers(60, n-1, size=cnt*2)[:cnt*2])
    sims.append(np.mean(rr)*100)
sims = np.array(sims)
pct = (sims < m_real).mean()*100
print(f"실제 신호        : {m_real:+.3f}%   (거래 {len(real)}건)")
print(f"무작위 진입일    : {sims.mean():+.3f}%   (40회, 표준편차 {sims.std():.3f}%p, 범위 {sims.min():+.3f}~{sims.max():+.3f}%)")
print(f"초과분           : {m_real - sims.mean():+.3f}%p")
print(f"퍼센타일         : {pct:.0f}")
print(f"판정             : {'신호에 우위 있음 (p<0.05)' if pct >= 95 else '신호와 무작위를 구분할 수 없음'}")

print()
print("="*104); print("참고 - 단순 보유 대비"); print("="*104)
bh = []
for code in per:
    c = KR[code]["df"]["Close"]
    days = len(c)
    bh.append(((c.iloc[-1]/c.iloc[0])**(1/days) - 1)*100)
print(f"유니버스 평균 일간수익률 : {np.mean(bh):+.4f}%/일")
print(f"전략 진입 1회당 보유일   : {real['held'].mean():.1f}일")
print(f"→ 단순 보유 시 같은 기간 기대수익 : {np.mean(bh)*real['held'].mean():+.3f}%")
print(f"→ 전략 실제                       : {m_real:+.3f}%")
expo = (len(real)*real['held'].mean()) / sum(len(KR[c]['df']) for c in per) * 100
print(f"시장 노출 시간 비중               : {expo:.1f}%")

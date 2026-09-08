# -*- coding: utf-8 -*-
"""완전 격리 검증: 2015~2020 으로만 파라미터를 고르고 2021~2026 은 손대지 않는다."""
import sys, os, itertools, warnings; warnings.filterwarnings("ignore"); sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from fast import run_fast
from engine import DEFAULT

GRID = {"max_hold":[3,5,8], "extended_max":[0.08,0.12,0.16], "dip_atr":[0.3,0.5,0.8],
        "tp1_atr":[1.0,1.5,2.0], "sh_max_loss":[0.025,0.035,0.045], "min_rr":[1.0,1.2,1.5]}
KEYS = list(GRID)
COMBOS = [dict(zip(KEYS,v)) for v in itertools.product(*GRID.values())]

def sc(R, mn=60):
    if len(R) < mn: return -99
    se = R.std(ddof=1)/np.sqrt(len(R))
    return R.mean()/se if se>0 else -99

# 훈련구간에서 상위 조합들을 모은다
scored = []
for cb in COMBOS:
    R,_ = run_fast({**DEFAULT, **cb}, y0=2015, y1=2020)
    scored.append((sc(R), cb, len(R), R.mean()*100))
scored.sort(key=lambda x: -x[0])

print("="*104); print("훈련 2015~2020 상위 10개 조합"); print("="*104)
for s, cb, n, m in scored[:10]:
    print(f"  t={s:+.2f} n={n:4d} 평균{m:+.3f}%  {cb}")

print()
print("="*104); print("각 파라미터가 상위 30개 조합에서 얼마나 자주 뽑혔나 (훈련구간 기준)"); print("="*104)
top = [cb for _,cb,_,_ in scored[:30]]
for k in KEYS:
    from collections import Counter
    c = Counter(cb[k] for cb in top)
    line = "  ".join(f"{v}:{n:2d}회" for v,n in sorted(c.items()))
    dom = c.most_common(1)[0]
    print(f"  {k:14s} {line:44s} → 최빈 {dom[0]} ({dom[1]}/30)")

best = scored[0][1]
print()
print("="*104); print("완전 격리 검증 2021~2026 (훈련에 한 번도 쓰이지 않음)"); print("="*104)
def ev(p, lab):
    R,H = run_fast({**DEFAULT, **p}, y0=2021, y1=2026)
    se = R.std(ddof=1)/np.sqrt(len(R)); eq = np.cumprod(1+R)
    print(f"{lab:34s}{len(R):>6d}거래  승률{(R>0).mean()*100:5.1f}%  평균{R.mean()*100:+.3f}%"
          f"  t={R.mean()/se:+.2f}  MDD{float((1-eq/np.maximum.accumulate(eq)).max()*100):5.1f}%")
    return R

ev({}, "현행 파라미터")
ev(best, f"훈련 최적 (1위 조합)")
ev({"min_rr":1.5,"tp1_atr":2.0}, "로버스트 (rr=1.5, tp1_atr=2.0)")
print(f"\n훈련 1위 조합: {best}")

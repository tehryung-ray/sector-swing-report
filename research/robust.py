# -*- coding: utf-8 -*-
"""폴드 전반에서 안정적인 파라미터만 채택했을 때의 아웃오브샘플 성과."""
import sys, os, warnings; warnings.filterwarnings("ignore"); sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from fast import run_fast
from engine import DEFAULT

OOS = (2021, 2026)

def ev(p, lab):
    R, H = run_fast({**DEFAULT, **p}, y0=OOS[0], y1=OOS[1])
    if len(R) < 10: return None
    se = R.std(ddof=1)/np.sqrt(len(R)); eq = np.cumprod(1+R)
    return dict(lab=lab, n=len(R), win=(R>0).mean()*100, m=R.mean()*100,
                t=R.mean()/se, cum=(eq[-1]-1)*100,
                mdd=float((1-eq/np.maximum.accumulate(eq)).max()*100), held=H.mean())

CAND = [
    ("현행", {}),
    ("min_rr 1.2→1.5", {"min_rr": 1.5}),
    ("tp1_atr 1.5→2.0", {"tp1_atr": 2.0}),
    ("max_hold 5→3", {"max_hold": 3}),
    ("sh_max_loss .035→.045", {"sh_max_loss": 0.045}),
    ("로버스트(rr+tp1)", {"min_rr": 1.5, "tp1_atr": 2.0}),
    ("로버스트+hold3", {"min_rr": 1.5, "tp1_atr": 2.0, "max_hold": 3}),
    ("로버스트+손절.045", {"min_rr": 1.5, "tp1_atr": 2.0, "sh_max_loss": 0.045}),
]
print("="*114); print(f"아웃오브샘플 {OOS[0]}~{OOS[1]} — 한 번에 한 가지씩 바꿔 기여도 확인"); print("="*114)
print(f"{'설정':24s}{'거래':>7}{'승률':>8}{'평균':>10}{'t':>7}{'누적':>10}{'MDD':>8}{'보유':>7}")
base = None
for lab, p in CAND:
    r = ev(p, lab)
    if r is None: continue
    if lab == "현행": base = r
    d = "" if lab == "현행" else f"  ({r['m']-base['m']:+.3f}%p)"
    print(f"{lab:24s}{r['n']:>7d}{r['win']:>7.1f}%{r['m']:>+9.3f}%{r['t']:>+7.2f}"
          f"{r['cum']:>+9.0f}%{r['mdd']:>7.1f}%{r['held']:>7.1f}{d}")

print()
print("="*114); print("연도별 - 특정 해에만 통하는 게 아닌지 확인"); print("="*114)
BEST = {"min_rr": 1.5, "tp1_atr": 2.0}
print(f"{'연도':>6}{'현행 거래':>10}{'현행 평균':>11}{'로버스트 거래':>13}{'로버스트 평균':>13}{'판정':>8}")
wins = 0
for y in range(2021, 2027):
    Rd,_ = run_fast(DEFAULT, y0=y, y1=y)
    Ro,_ = run_fast({**DEFAULT, **BEST}, y0=y, y1=y)
    if len(Rd) < 5 or len(Ro) < 5: continue
    ok = Ro.mean() > Rd.mean(); wins += ok
    print(f"{y:>6}{len(Rd):>10d}{Rd.mean()*100:>+10.3f}%{len(Ro):>13d}{Ro.mean()*100:>+12.3f}%{'개선' if ok else '악화':>8}")
print(f"\n{wins}/6 연도에서 개선")

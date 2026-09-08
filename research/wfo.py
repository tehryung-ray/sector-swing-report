# -*- coding: utf-8 -*-
"""워크포워드 최적화. 인샘플 최적값은 참고만 하고 아웃오브샘플로만 판정한다."""
import sys, os, itertools, warnings, time, json
warnings.filterwarnings("ignore"); sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from fast import run_fast
from engine import DEFAULT

GRID = {
    "max_hold":     [3, 5, 8],
    "extended_max": [0.08, 0.12, 0.16],
    "dip_atr":      [0.3, 0.5, 0.8],
    "tp1_atr":      [1.0, 1.5, 2.0],
    "sh_max_loss":  [0.025, 0.035, 0.045],
    "min_rr":       [1.0, 1.2, 1.5],
}
KEYS = list(GRID)
COMBOS = [dict(zip(KEYS, v)) for v in itertools.product(*GRID.values())]
MIN_TRAIN = 60
FOLDS = [(2015, y-1, y) for y in range(2021, 2027)]


def score(R):
    """훈련 목적함수 = t값. 효과크기와 표본수를 함께 반영한다."""
    if len(R) < MIN_TRAIN: return -99.0
    se = R.std(ddof=1)/np.sqrt(len(R))
    return R.mean()/se if se > 0 else -99.0


print(f"격자 {len(COMBOS)}조합 x {len(FOLDS)}폴드 = {len(COMBOS)*len(FOLDS)}회 백테스트")
t0 = time.time()
oos_def, oos_opt, picks = [], [], []

for tr0, tr1, te in FOLDS:
    best, bs = None, -1e9
    for cb in COMBOS:
        p = {**DEFAULT, **cb}
        R, _ = run_fast(p, y0=tr0, y1=tr1)
        s = score(R)
        if s > bs: bs, best = s, cb
    Rtr, _ = run_fast({**DEFAULT, **best}, y0=tr0, y1=tr1)
    Rd, _ = run_fast(DEFAULT, y0=te, y1=te)
    Ro, _ = run_fast({**DEFAULT, **best}, y0=te, y1=te)
    oos_def.append(Rd); oos_opt.append(Ro); picks.append(best)
    print(f"\n[훈련 {tr0}~{tr1} → 검증 {te}]")
    print(f"  선택 파라미터: {best}")
    print(f"  훈련  {len(Rtr):4d}거래 평균 {Rtr.mean()*100:+.3f}% (t={bs:+.2f})")
    print(f"  검증  현행 {len(Rd):3d}거래 {Rd.mean()*100:+.3f}%  |  최적 {len(Ro):3d}거래 {Ro.mean()*100:+.3f}%"
          f"  → {'개선' if len(Ro) and len(Rd) and Ro.mean() > Rd.mean() else '악화'}")

print(f"\n소요 {time.time()-t0:.0f}초")
D = np.concatenate([r for r in oos_def if len(r)])
O = np.concatenate([r for r in oos_opt if len(r)])
print(f"\n{'='*88}\n아웃오브샘플 종합 (2021~2026, 훈련에 쓰이지 않은 구간만)\n{'='*88}")
for lab, R in (("현행 파라미터", D), ("워크포워드 최적", O)):
    se = R.std(ddof=1)/np.sqrt(len(R))
    print(f"{lab:16s} {len(R):5d}거래  승률 {(R>0).mean()*100:5.1f}%  "
          f"평균 {R.mean()*100:+.3f}%  t={R.mean()/se:+.2f}  누적 {(np.cumprod(1+R)[-1]-1)*100:+.0f}%")
print(f"\n{'='*88}\n파라미터 안정성 - 폴드마다 같은 값이 뽑히는가\n{'='*88}")
for k in KEYS:
    vals = [p[k] for p in picks]
    uniq = len(set(vals))
    print(f"  {k:14s} {str(vals):46s} {'안정' if uniq <= 2 else '불안정(노이즈 의심)'}")
json.dump(picks, open(os.path.join(os.path.dirname(__file__), "picks.json"), "w"))

# -*- coding: utf-8 -*-
"""벡터화 엔진이 프로덕션 compute_levels+gates 와 같은 판단을 내리는지 검증."""
import sys, os, pickle, warnings, random
warnings.filterwarnings("ignore"); sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")); sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from engine import indicators, levels, DEFAULT
from pipeline.levels import compute_levels
from pipeline.gates import evaluate

d = pickle.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "all.pkl"), "rb"))
random.seed(3)
checked = agree = mismatch = 0
diffs = []
for code, v in d["kr"].items():
    df = v["df"]; ind = indicators(df)
    for i in random.sample(range(80, len(df)), min(60, len(df) - 80)):
        checked += 1
        fast = levels(ind.iloc[i], DEFAULT)
        lv = compute_levels(df.iloc[:i + 1])
        prod = None
        if lv is not None and not evaluate(lv, "strong"):
            prod = {"entry": lv["entry"], "tp1": lv["tp1"], "tp2": lv["tp2"], "stop": lv["stop"]}
        if (fast is None) != (prod is None):
            mismatch += 1
            diffs.append((code, df.index[i].date(), "통과여부 불일치",
                          fast is not None, prod is not None))
            continue
        if fast is None:
            agree += 1; continue
        bad = [k for k in ("entry", "tp1", "tp2", "stop") if fast[k] != prod[k]]
        if bad:
            mismatch += 1
            diffs.append((code, df.index[i].date(), f"가격 불일치 {bad}",
                          {k: fast[k] for k in bad}, {k: prod[k] for k in bad}))
        else:
            agree += 1

print(f"검증 {checked}건 | 일치 {agree} | 불일치 {mismatch}")
for x in diffs[:8]:
    print("  ", x)
print("\n결과:", "엔진 동등성 확인" if mismatch == 0 else "!! 불일치 있음 - 최적화 진행 불가")

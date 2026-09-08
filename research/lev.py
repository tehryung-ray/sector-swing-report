# -*- coding: utf-8 -*-
"""레버리지 ETF 검증 (최적화된 파라미터 기준).

기초 ETF 와 레버리지 ETF 를 같은 기간·같은 전략으로 돌려 비교한다.
'티커만 바꿔 넣으면 어떻게 되는가'가 핵심 질문이다.
"""
import sys, os, pickle, warnings
warnings.filterwarnings("ignore"); sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from engine import indicators, DEFAULT
import fast as F

PAIRS = [
    ("091160", "KODEX 반도체",       "494310", "KODEX 반도체레버리지",       "SOXX"),
    ("396500", "TIGER 반도체TOP10",  "488080", "TIGER 반도체TOP10레버리지",  "SOXX"),
    ("305720", "KODEX 2차전지산업",   "462330", "KODEX 2차전지산업레버리지",   "LIT"),
    ("364980", "TIGER 2차전지TOP10", "412570", "TIGER 2차전지TOP10레버리지", "LIT"),
    ("139260", "TIGER 200 IT",      "243880", "TIGER 200IT레버리지",       "XLK"),
    ("466920", "SOL 조선TOP3플러스",  "0080Y0", "SOL 조선TOP3플러스레버리지",  "XLI"),
    ("449450", "PLUS K방산",         "0104G0", "PLUS K방산레버리지",         "ITA"),
]

lev_raw = pickle.load(open(os.path.join(HERE, "lev_data.pkl"), "rb"))
US = F.US


def make_arrays(df, us_ticker):
    ind = indicators(df)
    a = {k: ind[k].values.astype(float) for k in
         ["close","open","high","low","ma20","ma60","sd20","low5","swing",
          "hi10","hi60","atr","turn","ma20_5"]}
    ud = US.get(us_ticker)
    c = ud["Close"]; ok = (c > c.rolling(20).mean())
    ok = ok.reindex(pd.date_range(c.index[0], "2026-12-31")).ffill().fillna(False)
    a["usok"] = ok.reindex(df.index).fillna(False).values.astype(bool)
    a["year"] = df.index.year.values
    return a


def run_one(df, us_t, p):
    """단일 종목 백테스트. fast.run_fast 와 동일 로직."""
    key = "__tmp__"
    F.A[key] = make_arrays(df, us_t)
    try:
        return F.run_fast(p, codes=[key])
    finally:
        F.A.pop(key, None)


def st(R, H):
    if len(R) < 5: return None
    se = R.std(ddof=1)/np.sqrt(len(R)); eq = np.cumprod(1+R); w = R > 0
    return dict(n=len(R), win=w.mean()*100, m=R.mean()*100, t=R.mean()/se,
                gain=R[w].mean()*100 if w.any() else 0,
                loss=R[~w].mean()*100 if (~w).any() else 0,
                cum=(eq[-1]-1)*100,
                mdd=float((1-eq/np.maximum.accumulate(eq)).max()*100), held=H.mean())


RUNS = [("기초", "b", {}),
        ("레버 (동일룰)", "l", {}),
        ("레버 (손절 2배)", "l", {"sh_min_loss": 0.040, "sh_max_loss": 0.070,
                               "pb_min_loss": 0.050, "pb_max_loss": 0.060})]
pool = {k: [[], []] for k, _, _ in RUNS}
HDR = f"{'구분':18s}{'거래':>6}{'승률':>8}{'평균':>9}{'t':>7}{'이익':>8}{'손실':>8}{'누적':>9}{'MDD':>8}{'보유':>6}"

print("="*104)
print("레버리지 재검증 — 최적화 파라미터 (min_rr=1.5, tp1_atr=2.0)")
print("="*104)
for bc, bn, lc, ln, ut in PAIRS:
    b, l = lev_raw[bc], lev_raw[lc]
    idx = b.index.intersection(l.index)
    if len(idx) < 140:
        print(f"\n[건너뜀] {bn} — 공통기간 {len(idx)}일"); continue
    B, L = b.loc[idx], l.loc[idx]
    print(f"\n{bn}  vs  {ln}   [{idx[0].date()}~{idx[-1].date()}, {len(idx)}일]")
    print(HDR)
    for lab, which, over in RUNS:
        R, H = run_one(B if which == "b" else L, ut, {**DEFAULT, **over})
        s = st(R, H)
        if s is None:
            print(f"{lab:18s}  (거래 부족)"); continue
        pool[lab][0].append(R); pool[lab][1].append(H)
        print(f"{lab:18s}{s['n']:>6d}{s['win']:>7.1f}%{s['m']:>+8.3f}%{s['t']:>+7.2f}"
              f"{s['gain']:>+7.2f}%{s['loss']:>+7.2f}%{s['cum']:>+8.0f}%{s['mdd']:>7.1f}%{s['held']:>6.1f}")

print(f"\n\n{'#'*104}\n전체 통합 (7쌍 거래를 한 표본으로)\n{'#'*104}")
print(HDR)
res = {}
for lab, _, _ in RUNS:
    if not pool[lab][0]: continue
    R = np.concatenate(pool[lab][0]); H = np.concatenate(pool[lab][1])
    s = st(R, H); res[lab] = R
    print(f"{lab:18s}{s['n']:>6d}{s['win']:>7.1f}%{s['m']:>+8.3f}%{s['t']:>+7.2f}"
          f"{s['gain']:>+7.2f}%{s['loss']:>+7.2f}%{s['cum']:>+8.0f}%{s['mdd']:>7.1f}%{s['held']:>6.1f}")

print(f"\n{'='*104}\n노출을 같게 맞추면 — 레버리지 2배는 절반 수량이면 기초 전량과 동일 노출\n{'='*104}")
print(f"{'구분':24s}{'거래당 기대값':>14}{'거래당 변동성':>14}{'수익/위험':>11}")
for lab in res:
    sc = 0.5 if lab.startswith("레버") else 1.0
    r = res[lab]*sc
    tag = lab + (" ½수량" if sc != 1 else "")
    print(f"{tag:24s}{r.mean()*100:>+13.3f}%{r.std(ddof=1)*100:>13.2f}%{r.mean()/r.std(ddof=1):>11.3f}")

print(f"\n{'='*104}\n부트스트랩 — 기초 대비 차이가 우연인가\n{'='*104}")
rng = np.random.default_rng(42)
base = res["기초"]
for lab in res:
    if lab == "기초": continue
    r = res[lab]
    d = [rng.choice(r, len(r), True).mean() - rng.choice(base, len(base), True).mean()
         for _ in range(4000)]
    d = np.array(d)*100
    lo, hi = np.percentile(d, [2.5, 97.5])
    verdict = "유의한 차이" if (lo > 0 or hi < 0) else "구분 불가 (신뢰구간이 0 포함)"
    print(f"{lab:18s} 차이 {d.mean():+.3f}%p  95%CI [{lo:+.3f}, {hi:+.3f}]  → {verdict}")

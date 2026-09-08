# -*- coding: utf-8 -*-
"""전체 22종목 합성 레버리지 검증. 실물은 상장기간이 짧아 표본이 부족하다."""
import sys, os, pickle, warnings
warnings.filterwarnings("ignore"); sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from engine import indicators, DEFAULT
from synth import synth_lev
import fast as F

# 실물 레버리지는 기초보다 거래대금이 적다(측정 중앙값 0.25배). 합성에도 반영한다.
LIQ = 0.25
WIDE = {"sh_min_loss":0.040, "sh_max_loss":0.070, "pb_min_loss":0.050, "pb_max_loss":0.060}

# 2배 차트에서는 모든 % 기준값이 기초 기준으로 절반 의미가 된다.
#   손절 -3%  = 기초 -1.5%      이격 12% = 기초 6%      눌림 4% = 기초 2%
# 따라서 손절만 넓히는 것으로는 부족하고, % 기준값 전체를 2배로 재조정해야
# 기초와 '같은 거래'를 하게 된다. min_rr 은 비율이라, dip_atr 은 ATR 단위라 척도 무관.
FULL = {**WIDE, "pullback_max":0.08, "extended_max":0.24, "min_upside":3.0}


def arrays(df, us_ticker, liq=1.0):
    ind = indicators(df)
    a = {k: ind[k].values.astype(float) for k in
         ["close","open","high","low","ma20","ma60","sd20","low5","swing",
          "hi10","hi60","atr","turn","ma20_5"]}
    a["turn"] = a["turn"] * liq
    c = F.US[us_ticker]["Close"]; ok = (c > c.rolling(20).mean())
    ok = ok.reindex(pd.date_range(c.index[0], "2026-12-31")).ffill().fillna(False)
    a["usok"] = ok.reindex(df.index).fillna(False).values.astype(bool)
    a["year"] = df.index.year.values
    return a


def run_all(kind, over=None, y0=None, y1=None):
    R, H = [], []
    for code, v in F.KR.items():
        df = v["df"]
        if kind == "lev":
            df = synth_lev(df)
        F.A["__t__"] = arrays(df, v["us"], LIQ if kind == "lev" else 1.0)
        try:
            r, h = F.run_fast({**DEFAULT, **(over or {})}, y0=y0, y1=y1, codes=["__t__"])
        finally:
            F.A.pop("__t__", None)
        if len(r): R.append(r); H.append(h)
    return np.concatenate(R), np.concatenate(H)


def st(R, H, lab):
    se = R.std(ddof=1)/np.sqrt(len(R)); eq = np.cumprod(1+R); w = R > 0
    return dict(lab=lab, n=len(R), win=w.mean()*100, m=R.mean()*100, t=R.mean()/se,
                gain=R[w].mean()*100, loss=R[~w].mean()*100,
                mdd=float((1-eq/np.maximum.accumulate(eq)).max()*100), held=H.mean())


HDR = f"{'구분':22s}{'거래':>7}{'승률':>8}{'평균':>9}{'t':>7}{'이익':>8}{'손실':>8}{'MDD':>8}{'보유':>6}"
def show(s):
    print(f"{s['lab']:22s}{s['n']:>7d}{s['win']:>7.1f}%{s['m']:>+8.3f}%{s['t']:>+7.2f}"
          f"{s['gain']:>+7.2f}%{s['loss']:>+7.2f}%{s['mdd']:>7.1f}%{s['held']:>6.1f}")

CASES = [("기초", "base", None), ("합성레버 (동일룰)", "lev", None),
         ("합성레버 (손절2배)", "lev", WIDE), ("합성레버 (전면재조정)", "lev", FULL)]
store = {}
for title, y0, y1 in [("전체기간 2015~2026", None, None), ("검증구간 2021~2026", 2021, 2026)]:
    print(f"\n{'='*96}\n{title}\n{'='*96}")
    print(HDR)
    for lab, kind, over in CASES:
        R, H = run_all(kind, over, y0, y1)
        show(st(R, H, lab))
        if y0 == 2021: store[lab] = R

print(f"\n{'='*96}\n노출 동일 기준 (레버리지 ½수량 = 기초 전량)  [2021~2026]\n{'='*96}")
print(f"{'구분':26s}{'거래당 기대값':>14}{'변동성':>11}{'수익/위험':>11}")
for lab, R in store.items():
    sc = 0.5 if "레버" in lab else 1.0
    r = R*sc; tag = lab + (" ½수량" if sc != 1 else "")
    print(f"{tag:26s}{r.mean()*100:>+13.3f}%{r.std(ddof=1)*100:>10.2f}%{r.mean()/r.std(ddof=1):>11.3f}")

print(f"\n{'='*96}\n부트스트랩 — 기초 대비 (½수량 기준, 노출 동일)  [2021~2026]\n{'='*96}")
rng = np.random.default_rng(42); base = store["기초"]
for lab, R in store.items():
    if lab == "기초": continue
    r = R*0.5
    d = np.array([rng.choice(r, len(r), True).mean() - rng.choice(base, len(base), True).mean()
                  for _ in range(4000)])*100
    lo, hi = np.percentile(d, [2.5, 97.5])
    print(f"{lab+' ½수량':26s} 차이 {d.mean():+.3f}%p  95%CI [{lo:+.3f}, {hi:+.3f}]"
          f"  → {'유의' if (lo>0 or hi<0) else '구분 불가'}")

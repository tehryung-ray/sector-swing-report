# -*- coding: utf-8 -*-
"""합성 2배 시계열 생성 및 실물 대조 검증.

레버리지 ETF 는 상장 기간이 짧아(2021~2025) 표본이 부족하다.
일일재조정 2배 상품은 '전일 종가 대비 당일 변동의 2배'로 정의되므로,
기초 ETF 의 OHLC 로 그대로 재구성할 수 있다. 실물과 대조해 타당성을 확인한 뒤 쓴다.
"""
import sys, os, pickle, warnings
warnings.filterwarnings("ignore"); sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
import numpy as np, pandas as pd


# 실물 레버리지 ETF 7종과 대조해 측정한 일평균 괴리.
# 합성이 실물보다 하루 +0.033%p 낙관적이다(스왑비용·리밸런싱 슬리피지·보수).
# 보수적으로 이만큼 차감해야 실물과 맞는다. 운용보수 차이(0.0008%/일)보다 40배 크다.
REAL_DRAG = 0.00033


def synth_lev(df, L=2.0, drag=REAL_DRAG):
    """기초 OHLCV -> 합성 L배 OHLCV. 실측 마찰을 일할 차감."""
    o, h, l, c, v = (df[x].values.astype(float) for x in ("Open","High","Low","Close","Volume"))
    n = len(c)
    SO, SH, SL, SC = (np.empty(n) for _ in range(4))
    SC[0] = SO[0] = SH[0] = SL[0] = 1000.0
    for i in range(1, n):
        pc = c[i-1]
        SO[i] = SC[i-1] * (1 + L*(o[i]/pc - 1))
        SH[i] = SC[i-1] * (1 + L*(h[i]/pc - 1))
        SL[i] = SC[i-1] * (1 + L*(l[i]/pc - 1))
        SC[i] = SC[i-1] * (1 + L*(c[i]/pc - 1) - drag)
    out = pd.DataFrame({"Open":SO,"High":SH,"Low":SL,"Close":SC,"Volume":v}, index=df.index)
    return out.iloc[1:]


if __name__ == "__main__":
    lev = pickle.load(open(os.path.join(HERE, "lev_data.pkl"), "rb"))
    PAIRS = [("091160","KODEX 반도체","494310"),("396500","TIGER 반도체TOP10","488080"),
             ("305720","KODEX 2차전지산업","462330"),("364980","TIGER 2차전지TOP10","412570"),
             ("139260","TIGER 200 IT","243880"),("466920","SOL 조선TOP3플러스","0080Y0"),
             ("449450","PLUS K방산","0104G0")]
    print("="*98)
    print("합성 2배 vs 실물 레버리지 ETF — 합성을 신뢰할 수 있는가")
    print("="*98)
    print(f"{'쌍':24s}{'표본':>6}{'일간수익 상관':>13}{'일평균 차이':>12}{'5일수익 상관':>13}{'추적오차(연)':>13}")
    for bc, bn, lc in PAIRS:
        b, real = lev[bc], lev[lc]
        idx = b.index.intersection(real.index)
        if len(idx) < 100: continue
        syn = synth_lev(b.loc[b.index <= idx[-1]]).reindex(idx).dropna()
        j = syn.index.intersection(real.index)
        rs = syn.loc[j,"Close"].pct_change().dropna()
        rr = real.loc[j,"Close"].pct_change().dropna()
        k = rs.index.intersection(rr.index)
        rs, rr = rs[k], rr[k]
        c1 = np.corrcoef(rs, rr)[0,1]
        d = (rs - rr)
        c5 = np.corrcoef(syn.loc[j,"Close"].pct_change(5).dropna().reindex(k).dropna(),
                         real.loc[j,"Close"].pct_change(5).dropna().reindex(k).dropna())[0,1]
        te = d.std()*np.sqrt(252)*100
        print(f"{bn[:22]:24s}{len(k):>6d}{c1:>13.4f}{d.mean()*100:>+11.4f}%{c5:>13.4f}{te:>12.2f}%")

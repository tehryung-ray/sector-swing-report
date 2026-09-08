# -*- coding: utf-8 -*-
"""numpy 백테스터. bt.py 와 동일 로직, 판다스 행 접근을 제거해 가속."""
import sys, os, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")); sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
from engine import indicators, DEFAULT

_D = pickle.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "all.pkl"), "rb"))
KR, US = _D["kr"], _D["us"]

KEYS = ["close","open","high","low","ma20","ma60","sd20","low5","swing",
        "hi10","hi60","atr","turn","ma20_5"]
A = {}
for code, v in KR.items():
    ind = indicators(v["df"])
    a = {k: ind[k].values.astype(float) for k in KEYS}
    a["dates"] = v["df"].index.values
    # 미국 섹터 필터를 한국 날짜에 맞춰 미리 정렬
    ud = US.get(v["us"])
    if ud is not None:
        c = ud["Close"]; ok = (c > c.rolling(20).mean())
        ok = ok.reindex(pd.date_range(c.index[0], "2026-12-31")).ffill().fillna(False)
        a["usok"] = ok.reindex(v["df"].index).fillna(False).values.astype(bool)
    else:
        a["usok"] = np.ones(len(v["df"]), bool)
    a["year"] = v["df"].index.year.values
    A[code] = a


def _tick(x, up=False):
    t = 1.0 if x < 2000 else 5.0
    return (np.ceil(x/t) if up else np.floor(x/t)) * t


def run_fast(p, y0=None, y1=None, codes=None):
    """반환: (수익률 배열, 보유일 배열)"""
    R, H = [], []
    for code in (codes or A):
        a = A[code]; n = len(a["close"])
        cl,op,hi,lo = a["close"],a["open"],a["high"],a["low"]
        ma20,ma60,sd20 = a["ma20"],a["ma60"],a["sd20"]
        low5,swing,hi10,hi60 = a["low5"],a["swing"],a["hi10"],a["hi60"]
        atr,turn,ma5,usok,yr = a["atr"],a["turn"],a["ma20_5"],a["usok"],a["year"]
        mh = p["max_hold"]
        i = 60
        while i < n-1:
            if (y0 and yr[i] < y0) or (y1 and yr[i] > y1): i += 1; continue
            if p["us_filter"] and not usok[i]: i += 1; continue
            last, m20, m60, at = cl[i], ma20[i], ma60[i], atr[i]
            if not (at > 0) or not np.isfinite(m60) or not np.isfinite(sd20[i]) \
               or not np.isfinite(hi60[i]) or last <= m20:
                i += 1; continue
            ext = (last-m20)/m20
            if ext > p["extended_max"]: i += 1; continue
            if not (m20 > m60 or (np.isfinite(ma5[i]) and m20 > ma5[i])): i += 1; continue
            if ext <= p["pullback_max"]:
                entry = max(m20, low5[i])
                tp1 = max(hi10[i], entry*(1+p["min_tp1"]))
                bb = m20 + 2*sd20[i]
                tp2 = min(bb, hi60[i])
                if tp2 <= tp1: tp2 = max(bb, hi60[i], tp1*1.04)
                stop = min(swing[i]*0.99, entry*(1-p["pb_min_loss"]))
                stop = max(min(stop, entry*(1-p["pb_min_loss"])), entry*(1-p["pb_max_loss"]))
            else:
                entry = max(low5[i], last - p["dip_atr"]*at)
                stop = max(min(entry-at, entry*(1-p["sh_min_loss"])), entry*(1-p["sh_max_loss"]))
                risk = entry-stop
                tp1 = entry + max(p["tp1_atr"]*at, p["tp1_risk"]*risk)
            entry = min(entry, last)
            e, s, t1 = _tick(entry), _tick(stop, True), _tick(tp1)
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
            R.append((px/fill-1) - p["cost"]); H.append(held)
            i = i + 1 + max(held, 1)
    return np.array(R), np.array(H)

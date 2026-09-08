# -*- coding: utf-8 -*-
"""고속 백테스트 엔진. pipeline.levels 와 동일 로직을 벡터화한 것."""
import sys, os, math, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np, pandas as pd
from pipeline.util import round_tick

DEFAULT = dict(
    pullback_max=0.04, extended_max=0.12,
    pb_min_loss=0.025, pb_max_loss=0.030,
    sh_min_loss=0.020, sh_max_loss=0.035,
    dip_atr=0.5, min_tp1=0.025,
    tp1_atr=1.5, tp1_risk=1.3, tp2_atr=3.0, tp2_risk=2.5,
    min_rr=1.2, min_turnover=5.0, min_upside=1.5,
    max_hold=5, us_filter=True, cost=0.001,
)


def indicators(df):
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    ind = pd.DataFrame({
        "close": c, "open": df["Open"], "high": h, "low": l,
        "ma20": c.rolling(20).mean(), "ma60": c.rolling(60).mean(),
        "sd20": c.rolling(20).std(),
        "low5": l.rolling(5).min(), "swing": l.rolling(20).min(),
        "hi10": h.rolling(10).max(), "hi60": h.rolling(60).max(),
        "atr": tr.rolling(14).mean(),
        # 프로덕션은 표시용으로 1자리 반올림한 값으로 게이트를 비교한다. 동등성을 위해 맞춘다.
        "turn": ((c * v).rolling(20).mean() / 1e8).round(1),
    })
    ind["ma20_5"] = ind["ma20"].shift(5)
    return ind


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def levels(r, p):
    """지표 한 행 -> 가격대. None 이면 진입 불가."""
    last, ma20, ma60 = r["close"], r["ma20"], r["ma60"]
    if not np.isfinite([last, ma20, ma60, r["sd20"], r["low5"], r["swing"],
                        r["hi10"], r["hi60"], r["atr"]]).all() or r["atr"] <= 0:
        return None
    if last <= ma20:
        return None                                    # 하락추세
    ext = (last - ma20) / ma20
    if ext > p["extended_max"]:
        return None                                    # 과열
    # 중기추세: 정배열이거나 20일선 상승 중
    if not (ma20 > ma60 or (np.isfinite(r["ma20_5"]) and ma20 > r["ma20_5"])):
        return None

    if ext <= p["pullback_max"]:
        entry = max(ma20, r["low5"])
        tp1 = max(r["hi10"], entry * (1 + p["min_tp1"]))
        tp2 = min(ma20 + 2 * r["sd20"], r["hi60"])
        if tp2 <= tp1:
            tp2 = max(ma20 + 2 * r["sd20"], r["hi60"], tp1 * 1.04)
        stop = _clamp(min(r["swing"] * 0.99, entry * (1 - p["pb_min_loss"])),
                      entry * (1 - p["pb_max_loss"]), entry * (1 - p["pb_min_loss"]))
    else:
        entry = max(r["low5"], last - p["dip_atr"] * r["atr"])
        stop = _clamp(entry - r["atr"], entry * (1 - p["sh_max_loss"]),
                      entry * (1 - p["sh_min_loss"]))
        risk = entry - stop
        tp1 = entry + max(p["tp1_atr"] * r["atr"], p["tp1_risk"] * risk)
        tp2 = entry + max(p["tp2_atr"] * r["atr"], p["tp2_risk"] * risk)
    entry = min(entry, last)

    e = round_tick(entry, "down"); t1 = round_tick(tp1, "down")
    t2 = round_tick(tp2, "down"); s = round_tick(stop, "up")
    if s >= e or t1 <= e:
        return None
    rr = (t1 - e) / (e - s)
    up = (t1 / e - 1) * 100
    if rr < p["min_rr"] or up < p["min_upside"] or r["turn"] < p["min_turnover"]:
        return None
    return {"entry": e, "tp1": t1, "tp2": t2, "stop": s, "rr": rr}

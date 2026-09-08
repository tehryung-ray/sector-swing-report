# -*- coding: utf-8 -*-
import sys, os, io, pickle, warnings, yaml
warnings.filterwarnings("ignore"); sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import FinanceDataReader as fdr
from pipeline.sources.us import fetch_us

kr_cfg = yaml.safe_load(io.open(os.path.join(ROOT, "config/kr_universe.yaml"), encoding="utf-8"))
us_cfg = yaml.safe_load(io.open(os.path.join(ROOT, "config/us_sectors.yaml"), encoding="utf-8"))

kr = {}
for e in kr_cfg["etfs"]:
    try:
        df = fdr.DataReader(e["code"], "2015-01-01")[["Open","High","Low","Close","Volume"]].dropna(how="all")
        if len(df) > 200:
            kr[e["code"]] = {"name": e["name"], "us": e["us"], "df": df}
            print(f"{e['code']:8s}{e['name'][:24]:26s}{len(df):5d}행  {df.index[0].date()}~{df.index[-1].date()}")
    except Exception as ex:
        print(f"{e['code']} 실패 {ex}")

us = fetch_us([s["ticker"] for s in us_cfg["sectors"]] + [us_cfg["benchmark"]], period="max")
print(f"\n미국 {len(us)}종목, SPY {len(us['SPY'])}행 {us['SPY'].index[0].date()}~")
pickle.dump({"kr": kr, "us": us}, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "all.pkl"), "wb"))
tot = sum(len(v["df"]) for v in kr.values())
print(f"\n한국 {len(kr)}종목 총 {tot:,}행")

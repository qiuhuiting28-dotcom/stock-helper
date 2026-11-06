#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股看盤小幫手 — 每日資料更新
來源：
  上市清單：證交所 OpenAPI STOCK_DAY_ALL（名稱＋成交金額）
  上櫃清單：櫃買中心 OpenAPI tpex_mainboard_quotes（名稱＋成交金額）
  價格/日線：Yahoo Finance chart（上市 .TW、上櫃 .TWO）
  三大法人：證交所 BFI82U
用法：python update.py data.json [上市檔數=90] [上櫃檔數=30]
"""
import json, ssl, sys, time, re, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
DEFAULT_WATCH = ["2330","2317","2412","2882","1301","2603","2002"]
DEFAULT_NAMES = {"2330":"台積電","2317":"鴻海","2412":"中華電","2882":"國泰金",
                 "1301":"台塑","2603":"長榮","2002":"中鋼"}
FORCE = [("1503","士電",".TW"), ("6173","信昌電",".TWO"), ("8069","元太",".TWO")]   # 一定保留的股票
TWSE_N, TPEX_N = 90, 30
UA = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def http_get(url, insecure=False, timeout=25, tries=4):
    ctx=None
    if insecure:
        ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    last=None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout, context=ctx) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last=e; time.sleep([15,30,60,90][min(i,3)] if e.code==429 else 1.5*(i+1))
        except Exception as e:
            last=e; time.sleep(1.5*(i+1))
    raise last

def _num(x):
    try: return float(str(x).replace(",","") or 0)
    except: return 0.0

def fetch_twse_list():
    """上市股票 -> [(成交金額, code, name)] 由大到小（CSV 優先，OpenAPI 備援）"""
    # 1) 官方 CSV：STOCK_DAY_ALL
    try:
        raw = http_get("https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json", insecure=True)
        text = raw.decode("utf-8-sig").lstrip()
        if text.startswith("{"):
            rows = json.loads(text).get("data", [])
            items = []
            for r in rows:
                if isinstance(r, list) and len(r) >= 3:
                    code, name = str(r[0]).strip(), str(r[1]).strip()
                    if re.fullmatch(r"\d{4,6}", code) and name:
                        items.append((_num(r[4] if len(r) > 4 else 0), code, name))
            items.sort(reverse=True)
            if len(items) > 50: return items
        elif "證券代號" in text:
            import csv, io
            rdr = csv.DictReader(io.StringIO(text)); items = []
            for r in rdr:
                code = (r.get("證券代號") or "").strip(); name = (r.get("證券名稱") or "").strip()
                if not re.fullmatch(r"\d{4,6}", code) or not name: continue
                items.append((_num(r.get("成交金額")), code, name))
            items.sort(reverse=True)
            if len(items) > 50: return items
    except Exception as e:
        print("  [warn] 上市 CSV 失敗：", e, file=sys.stderr)
    # 2) OpenAPI JSON
    try:
        rows = json.loads(http_get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", insecure=True))
        items = []
        for r in rows:
            code = str(r.get("Code", "")).strip(); name = str(r.get("Name", "")).strip()
            if not re.fullmatch(r"\d{4,6}", code) or not name: continue
            items.append((_num(r.get("TradeValue")), code, name))
        items.sort(reverse=True)
        if len(items) > 50: return items
    except Exception as e:
        print("  [warn] 上市 OpenAPI 失敗：", e, file=sys.stderr)
    return []

def fetch_tpex_list():
    """上櫃股票 -> [(成交金額, code, name)] 由大到小"""
    try:
        rows=json.loads(http_get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", insecure=True))
        items=[]
        for r in rows:
            code=str(r.get("SecuritiesCompanyCode","")).strip(); name=str(r.get("CompanyName","")).strip()
            if not re.fullmatch(r"\d{4,6}", code) or not name: continue
            items.append((_num(r.get("TransactionAmount")), code, name))
        items.sort(reverse=True); return items
    except Exception as e:
        print("  [warn] 上櫃清單失敗：", e, file=sys.stderr); return []

def build_universe(n_twse, n_tpex):
    twse=fetch_twse_list(); tpex=fetch_tpex_list()
    name_of={c:n for _,c,n in twse}; name_of.update({c:n for _,c,n in tpex})
    sel=[]; seen=set()
    def add(code,name,suf):
        if code in seen: return
        seen.add(code); sel.append((code,name,suf))
    for _,c,n in twse[:n_twse]: add(c,n,".TW")
    for _,c,n in tpex[:n_tpex]: add(c,n,".TWO")
    twse_codes={x[1] for x in twse}
    for c in DEFAULT_WATCH:
        nm = name_of.get(c) or DEFAULT_NAMES.get(c)
        if nm: add(c, nm, ".TW" if (c in twse_codes or c not in name_of) else ".TWO")
    for c,n,suf in FORCE: add(c,n,suf)
    return sel, len(twse), len(tpex)

def yahoo_chart(symbol, rng="1y"):
    j=json.loads(http_get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={rng}&interval=1d&events=div"))
    res=j["chart"]["result"][0]; q=res["indicators"]["quote"][0]
    bars=[]
    for i,c in enumerate(q["close"]):
        if c is None: continue
        o=q["open"][i]; h=q["high"][i]; l=q["low"][i]
        bars.append({"o":o if o else c,"h":h if h else c,"l":l if l else c,"c":c,"v":q["volume"][i] or 0})
    divs=[{"t":int(k),"a":d.get("amount",0)} for k,d in res.get("events",{}).get("dividends",{}).items()]
    return bars, divs

def mean(a): return sum(a)/len(a) if a else 0.0
def pct(a,b): return (a-b)/b*100 if b else 0.0
r2=lambda x: round(x,2)

def build_stock(code,name,suf):
    bars,divs=yahoo_chart(code+suf)
    if len(bars)<2: raise RuntimeError("日線不足")
    last,prev=bars[-1],bars[-2]
    closes=[b["c"] for b in bars]; highs=[b["h"] for b in bars]; lows=[b["l"] for b in bars]; vols=[b["v"] for b in bars]
    price,prevc=last["c"],prev["c"]
    lo30,hi30=min(lows[-30:]),max(highs[-30:])
    avgVol=mean(vols[-20:])
    now=datetime.now(tz=TZ).timestamp()
    dy=(sum(d["a"] for d in divs if now-d["t"]<=365*86400)/price*100) if price else 0.0
    return {"code":code,"name":name,"price":r2(price),"prev":r2(prevc),
        "open":r2(last["o"]),"high":r2(last["h"]),"low":r2(last["l"]),
        "vol":int(round(last["v"]/1000)),"avgVol":int(round(avgVol/1000)),
        "ma5":r2(mean(closes[-5:])),"ma20":r2(mean(closes[-20:])),
        "ma60":r2(mean(closes[-60:]) if len(closes)>=60 else mean(closes)),
        "ma240":r2(mean(closes[-240:]) if len(closes)>=240 else mean(closes)),
        "lo30":r2(lo30),"hi30":r2(hi30),
        "lo60":r2(min(lows[-60:])),"hi60":r2(max(highs[-60:])),
        "lo240":r2(min(lows[-240:])),"hi240":r2(max(highs[-240:])),
        "sup":r2(lo30),"prs":r2(hi30),"dy":round(dy,1),
        "spark":[r2(c) for c in closes[-5:]]}

def build_index():
    bars,_=yahoo_chart("^TWII")
    closes=[b["c"] for b in bars]; last,prev=bars[-1]["c"],bars[-2]["c"]
    return {"value":r2(last),"prevClose":r2(prev),"chg":r2(last-prev),"chgPct":r2(pct(last,prev)),
            "volume":"—","time":datetime.now(tz=TZ).strftime("%H:%M"),"series":[r2(c) for c in closes[-30:]]}

LEGAL_MAP={"外資及陸資":"外資","外資":"外資","投信":"投信","自營商":"自營商"}
def build_legal():
    try:
        j=json.loads(http_get("https://www.twse.com.tw/rwd/zh/fund/BFI82U?dayDate=&type=day", insecure=True))
        out=[]
        for row in j.get("data",[]):
            nm=(row[0] or "").replace(" ","")
            for k,v in LEGAL_MAP.items():
                if k in nm and not any(o["who"]==v for o in out):
                    out.append({"who":v,"amt":round(_num(row[3])/1e8,1)}); break
        out.sort(key=lambda x:{"外資":0,"投信":1,"自營商":2}.get(x["who"],9)); return out
    except Exception as e:
        print("  [warn] 三大法人失敗：", e, file=sys.stderr); return []

def main():
    out_path=sys.argv[1] if len(sys.argv)>1 else "data.json"
    n_twse=int(sys.argv[2]) if len(sys.argv)>2 else TWSE_N
    n_tpex=int(sys.argv[3]) if len(sys.argv)>3 else TPEX_N
    sel,tw,te=build_universe(n_twse,n_tpex)
    print(f"清單：上市 {tw} 檔/上櫃 {te} 檔 → 選 {len(sel)} 檔")
    stocks=[]
    for i,(code,name,suf) in enumerate(sel,1):
        try:
            s=build_stock(code,name,suf); stocks.append(s)
            print(f"  [{i}/{len(sel)}] {code}{suf} {name} {s['price']}")
        except Exception as e:
            print(f"  [{i}/{len(sel)}] x {code}{suf} {name}: {e}", file=sys.stderr)
        time.sleep(0.8)
    try: idx=build_index()
    except Exception as e:
        print("  [warn] 指數失敗：", e, file=sys.stderr); idx={"value":0,"prevClose":0,"chg":0,"chgPct":0,"volume":"—","time":"—","series":[]}
    legal=build_legal(); now=datetime.now(tz=TZ)
    payload={"updated":now.strftime("%Y-%m-%d %H:%M"),"session":"盤中" if 9<=now.hour<14 else "非交易時段",
             "index":idx,"stocks":stocks,"legal":legal}
    with open(out_path,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,indent=1)
    print(f"\n寫出 {out_path}：{len(stocks)} 檔，更新 {payload['updated']}（{payload['session']}）")

if __name__=="__main__": main()

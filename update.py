#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股看盤小幫手 — 每日資料更新
資料來源（免費、免金鑰）：
  - 證交所 OpenAPI STOCK_DAY_ALL：全部上市股票名稱、成交金額（用來挑清單）
  - Yahoo Finance chart：個股/指數 即時價 + 近一年日線（算均線）
  - 證交所 BFI82U：三大法人買賣超
輸出：data.json
用法：python update.py data.json [股票檔數，預設120]
"""
import json, ssl, sys, time, re, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
DEFAULT_WATCH = ["2330","2317","2412","2882","1301","2603","2002"]
TOP_N = 120
UA = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def http_get(url, insecure=False, timeout=25, tries=4):
    ctx = None
    if insecure:
        ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout, context=ctx) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            time.sleep([15,30,60,90][min(i,3)] if e.code == 429 else 1.5*(i+1))
        except Exception as e:
            last = e; time.sleep(1.5*(i+1))
    raise last

def fetch_universe():
    """回傳 (選中的 [(code,name)...], 全部 code->name, 總檔數)。失敗回 ([],{},0)"""
    try:
        rows = json.loads(http_get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", insecure=True))
        items = []
        for r in rows:
            code = str(r.get("Code","")).strip(); name = str(r.get("Name","")).strip()
            if not re.fullmatch(r"\d{4,6}", code):   # 排除權證/特別股
                continue
            if not name or name.startswith("主動"):   # 排除主動式ETF雜訊（可留可不留）
                pass
            try: val = float(str(r.get("TradeValue","0")).replace(",","") or 0)
            except: val = 0
            items.append((val, code, name))
        items.sort(reverse=True)
        names = {c: n for _, c, n in items}
        sel = [(c, n) for _, c, n in items[:TOP_N]]
        have = {c for c, _ in sel}
        for c in DEFAULT_WATCH:                      # 固定保留預設持股
            if c not in have and c in names:
                sel.append((c, names[c]))
        return sel, names, len(items)
    except Exception as e:
        print("  [warn] 證交所清單抓取失敗：", e, file=sys.stderr)
        return [], {}, 0

def yahoo_chart(symbol, rng="1y"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={rng}&interval=1d&events=div"
    j = json.loads(http_get(url))
    res = j["chart"]["result"][0]
    ts = res["timestamp"]; q = res["indicators"]["quote"][0]
    bars = []
    for i, t in enumerate(ts):
        c = q["close"][i]
        if c is None: continue
        bars.append({"o": q["open"][i] if q["open"][i] is not None else c,
                     "h": q["high"][i] if q["high"][i] is not None else c,
                     "l": q["low"][i] if q["low"][i] is not None else c,
                     "c": c, "v": q["volume"][i] or 0})
    divs = [{"t": int(k), "a": d.get("amount",0)} for k, d in res.get("events",{}).get("dividends",{}).items()]
    return bars, divs

def mean(a): return sum(a)/len(a) if a else 0.0
def pct(a,b): return (a-b)/b*100 if b else 0.0
r2 = lambda x: round(x, 2)

def build_stock(code, name):
    bars, divs = yahoo_chart(code + ".TW")
    if len(bars) < 2: raise RuntimeError("日線不足")
    last, prev = bars[-1], bars[-2]
    closes=[b["c"] for b in bars]; highs=[b["h"] for b in bars]; lows=[b["l"] for b in bars]; vols=[b["v"] for b in bars]
    price, prevc = last["c"], prev["c"]
    ma5=mean(closes[-5:]); ma20=mean(closes[-20:])
    ma60=mean(closes[-60:]) if len(closes)>=60 else mean(closes)
    ma240=mean(closes[-240:]) if len(closes)>=240 else mean(closes)
    lo30,hi30=min(lows[-30:]),max(highs[-30:]); lo60,hi60=min(lows[-60:]),max(highs[-60:])
    lo240,hi240=min(lows[-240:]),max(highs[-240:])
    avgVol=mean(vols[-20:])
    now=datetime.now(tz=TZ).timestamp()
    dy_sum=sum(d["a"] for d in divs if now-d["t"]<=365*86400)
    dy=(dy_sum/price*100) if price else 0.0
    return {"code":code,"name":name,
        "price":r2(price),"prev":r2(prevc),"open":r2(last["o"]),"high":r2(last["h"]),"low":r2(last["l"]),
        "vol":int(round(last["v"]/1000)),"avgVol":int(round(avgVol/1000)),
        "ma5":r2(ma5),"ma20":r2(ma20),"ma60":r2(ma60),"ma240":r2(ma240),
        "lo30":r2(lo30),"hi30":r2(hi30),"lo60":r2(lo60),"hi60":r2(hi60),
        "lo240":r2(lo240),"hi240":r2(hi240),
        "sup":r2(lo30),"prs":r2(hi30),"dy":round(dy,1),
        "spark":[r2(c) for c in closes[-5:]]}

def build_index():
    bars,_ = yahoo_chart("%5ETWII".replace("%5E","^"))
    closes=[b["c"] for b in bars]; last,prev=bars[-1]["c"],bars[-2]["c"]
    return {"value":r2(last),"prevClose":r2(prev),"chg":r2(last-prev),"chgPct":r2(pct(last,prev)),
            "volume":"—","time":datetime.now(tz=TZ).strftime("%H:%M"),
            "series":[r2(c) for c in closes[-30:]]}

LEGAL_MAP={"外資及陸資":"外資","外資":"外資","投信":"投信","自營商":"自營商"}
def build_legal():
    try:
        j=json.loads(http_get("https://www.twse.com.tw/rwd/zh/fund/BFI82U?dayDate=&type=day", insecure=True))
        out=[]
        for row in j.get("data",[]):
            nm=(row[0] or "").replace(" ","")
            for k,v in LEGAL_MAP.items():
                if k in nm and not any(o["who"]==v for o in out):
                    out.append({"who":v,"amt":round(float(str(row[3]).replace(",",""))/1e8,1)}); break
        out.sort(key=lambda x:{"外資":0,"投信":1,"自營商":2}.get(x["who"],9))
        return out
    except Exception as e:
        print("  [warn] 三大法人失敗：", e, file=sys.stderr); return []

def main():
    global TOP_N
    out_path = sys.argv[1] if len(sys.argv)>1 else "data.json"
    n = int(sys.argv[2]) if len(sys.argv)>2 else TOP_N
    TOP_N = n

    sel, names, total = fetch_universe()
    if not sel:
        # 證交所失敗時，至少保留預設持股
        sel = [(c, c) for c in DEFAULT_WATCH]
    print(f"清單：選 {len(sel)} 檔（全市場 {total} 檔）")

    stocks=[]
    for i,(code,name) in enumerate(sel, 1):
        try:
            s=build_stock(code,name); stocks.append(s)
            print(f"  [{i}/{len(sel)}] {code} {name} {s['price']}")
        except Exception as e:
            print(f"  [{i}/{len(sel)}] x {code} {name}: {e}", file=sys.stderr)
        time.sleep(0.8)
    try: idx=build_index()
    except Exception as e:
        print("  [warn] 指數失敗：", e, file=sys.stderr)
        idx={"value":0,"prevClose":0,"chg":0,"chgPct":0,"volume":"—","time":"—","series":[]}
    legal=build_legal()
    now=datetime.now(tz=TZ)
    payload={"updated":now.strftime("%Y-%m-%d %H:%M"),
             "session":"盤中" if 9<=now.hour<14 else "非交易時段",
             "index":idx,"stocks":stocks,"legal":legal}
    with open(out_path,"w",encoding="utf-8") as f:
        json.dump(payload,f,ensure_ascii=False,indent=1)
    print(f"\n寫出 {out_path}：{len(stocks)} 檔，更新於 {payload['updated']}（{payload['session']}）")

if __name__=="__main__":
    main()

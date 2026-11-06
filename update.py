#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股看盤小幫手 — 每日資料更新腳本
資料來源（免費、免金鑰）：
  - Yahoo Finance chart API：個股/指數 即時價 + 近一年日線（算均線用）
  - 台灣證交所 BFI82U：三大法人買賣超金額
輸出：data.json（網頁讀這支）
設計：09:05 抓「昨收＋今日開盤」，13:45 抓「當日收盤完整」
"""
import json, ssl, sys, time, re, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))  # Asia/Taipei

# 自選股宇宙（可在這裡增減；代號需為上市 .TW）
UNIVERSE = [
    ("2330","台積電"),("2317","鴻海"),("2454","聯發科"),("2412","中華電"),
    ("2882","國泰金"),("1301","台塑"),("2603","長榮"),("2002","中鋼"),
    ("2308","台達電"),("2881","富邦金"),("2891","中信金"),("1216","統一"),
    ("2609","陽明"),("2886","兆豐金"),("1101","台泥"),("2382","廣達"),
    ("2303","聯電"),("2884","玉山金"),("1326","台化"),("2207","和泰車"),
    ("2474","可成"),("3008","大立光"),
]

UA = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def http_get(url, insecure=False, timeout=20, tries=3):
    ctx = None
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(1.2*(i+1))
    raise last

def yahoo_chart(symbol, rng="1y"):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?range={rng}&interval=1d&events=div")
    raw = http_get(url)
    j = json.loads(raw)
    res = j["chart"]["result"][0]
    meta = res["meta"]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    bars = []
    for i, t in enumerate(ts):
        c = q["close"][i]
        if c is None:
            continue
        bars.append({
            "t": t,
            "o": q["open"][i] if q["open"][i] is not None else c,
            "h": q["high"][i] if q["high"][i] is not None else c,
            "l": q["low"][i] if q["low"][i] is not None else c,
            "c": c,
            "v": q["volume"][i] or 0,
        })
    divs = []
    ev = res.get("events", {}).get("dividends", {})
    for k, d in ev.items():
        divs.append({"t": int(k), "a": d.get("amount", 0)})
    return meta, bars, divs

def mean(a): return sum(a)/len(a) if a else 0.0

def pct(a, b): return (a-b)/b*100 if b else 0.0

def build_stock(code, name):
    meta, bars, divs = yahoo_chart(code + ".TW")
    if len(bars) < 2:
        raise RuntimeError(f"{code} 日線不足")
    last = bars[-1]; prev = bars[-2]
    closes = [b["c"] for b in bars]
    highs  = [b["h"] for b in bars]
    lows   = [b["l"] for b in bars]
    vols   = [b["v"] for b in bars]

    price = last["c"]; prevc = prev["c"]
    ma5   = mean(closes[-5:])
    ma20  = mean(closes[-20:])
    ma60  = mean(closes[-60:]) if len(closes) >= 60 else mean(closes)
    ma240 = mean(closes[-240:]) if len(closes) >= 240 else mean(closes)
    lo30, hi30 = min(lows[-30:]), max(highs[-30:])
    lo60, hi60 = min(lows[-60:]), max(highs[-60:])
    lo240, hi240 = min(lows[-240:]), max(highs[-240:])
    avgVol = mean(vols[-20:])  # 股
    # 近一年股息合計 → 殖利率
    now = datetime.now(tz=TZ).timestamp()
    dy_sum = sum(d["a"] for d in divs if now - d["t"] <= 365*86400)
    dy = (dy_sum / price * 100) if price else 0.0

    r = lambda x: round(x, 2)
    return {
        "code": code, "name": name,
        "price": r(price), "prev": r(prevc),
        "open": r(last["o"]), "high": r(last["h"]), "low": r(last["l"]),
        "vol": int(round(last["v"]/1000)),          # 張
        "avgVol": int(round(avgVol/1000)),           # 張（20日均量）
        "ma5": r(ma5), "ma20": r(ma20), "ma60": r(ma60), "ma240": r(ma240),
        "lo30": r(lo30), "hi30": r(hi30),
        "lo60": r(lo60), "hi60": r(hi60),
        "lo240": r(lo240), "hi240": r(hi240),
        "sup": r(lo30), "prs": r(hi30),              # 支撐/壓力：取近30日低/高
        "dy": round(dy, 1),
        "spark": [round(c, 2) for c in closes[-5:]],
    }

def build_index():
    meta, bars, _ = yahoo_chart("%5ETWII")
    closes = [b["c"] for b in bars]
    last, prev = bars[-1]["c"], bars[-2]["c"]
    return {
        "value": round(last, 2),
        "prevClose": round(prev, 2),
        "chg": round(last-prev, 2),
        "chgPct": round(pct(last, prev), 2),
        "volume": "—",
        "time": datetime.now(tz=TZ).strftime("%H:%M"),
        "series": [round(c, 2) for c in closes[-30:]],
    }

LEGAL_MAP = {"外資及陸資":"外資", "外資":"外資", "投信":"投信", "自營商":"自營商"}

def build_legal():
    """三大法人買賣超（億元），證交所 BFI82U。抓不到就回空。"""
    try:
        # 證交所憑證在某些 Python 環境會驗證失敗，這裡用 insecure 取公開資料
        raw = http_get("https://www.twse.com.tw/rwd/zh/fund/BFI82U?dayDate=&type=day", insecure=True)
        j = json.loads(raw)
        rows = j.get("data", [])
        out = []
        for row in rows:
            nm = (row[0] or "").replace(" ", "")
            key = None
            for k in LEGAL_MAP:
                if k in nm:
                    key = LEGAL_MAP[k]; break
            if key and not any(o["who"] == key for o in out):
                # row: [名稱, 買進金額, 賣出金額, 買賣超金額]
                net = float(str(row[3]).replace(",", "")) / 1e8
                out.append({"who": key, "amt": round(net, 1)})
        order = {"外資":0, "投信":1, "自營商":2}
        out.sort(key=lambda x: order.get(x["who"], 9))
        return out
    except Exception as e:
        print("  [warn] 三大法人抓取失敗：", e, file=sys.stderr)
        return []

def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "data.json"
    stocks = []
    for code, name in UNIVERSE:
        try:
            s = build_stock(code, name)
            stocks.append(s)
            print(f"  OK {code} {name} {s['price']}")
        except Exception as e:
            print(f"  x  {code} {name}: {e}", file=sys.stderr)
        time.sleep(0.35)  # 客氣一點，避免被限流
    try:
        idx = build_index()
    except Exception as e:
        print("  [warn] 指數抓取失敗：", e, file=sys.stderr)
        idx = {"value":0,"prevClose":0,"chg":0,"chgPct":0,"volume":"—","time":"—","series":[]}
    legal = build_legal()

    now = datetime.now(tz=TZ)
    payload = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "session": "盤中" if (9 <= now.hour < 14) else "非交易時段",
        "index": idx,
        "stocks": stocks,
        "legal": legal,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"\n寫出 {out_path}：{len(stocks)} 檔，更新於 {payload['updated']}（{payload['session']}）")

if __name__ == "__main__":
    main()

"""Save a month of 15-minute crypto market history for offline study (PUBLIC DATA ONLY).

research/data/history15m.json.gz contains:
  markets: ticker, series, open, close, target (Kalshi floor_strike), result
  kalshi:  per market, 1-minute YES bid/ask/volume from Kalshi candlesticks
  price:   per series, 1-minute composite (mean of Coinbase + Bitstamp) open/high/low/close and summed volume
"""
import functools, gzip, json, math, os, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

print = functools.partial(print, flush=True)
K = "https://api.elections.kalshi.com/trade-api/v2"
CB = "https://api.exchange.coinbase.com"
UA = {"User-Agent": "kalshi-data-research/1.0"}
SERIES = {"KXBTC15M": "BTC-USD", "KXETH15M": "ETH-USD", "KXSOL15M": "SOL-USD"}
BS = {"BTC-USD": "btcusd", "ETH-USD": "ethusd", "SOL-USD": "solusd"}
DAYS = 31
http = requests.Session()


def get(url, params=None, tries=4):
    for i in range(tries):
        try:
            r = http.get(url, params=params, headers=UA, timeout=10)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(1.5 * (i + 1)); continue
            if r.status_code >= 400:
                return None
            return r.json()
        except requests.RequestException:
            time.sleep(1.5 * (i + 1))
    return None


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def dollars(c, key):
    if not c: return None
    if c.get(key + "_dollars") not in (None, ""): return round(float(c[key + "_dollars"]), 4)
    if c.get(key) is not None: return round(float(c[key]) / 100, 4)
    return None


now = int(time.time()); start = now - DAYS * 86400
markets = []
for s in SERIES:
    cursor = None
    for _ in range(80):
        p = {"series_ticker": s, "status": "settled", "limit": 1000, "min_close_ts": start, "max_close_ts": now}
        if cursor: p["cursor"] = cursor
        j = get(f"{K}/markets", p) or {}
        for m in j.get("markets", []):
            if m.get("result") in ("yes", "no") and m.get("floor_strike") is not None:
                markets.append({"t": m["ticker"], "s": s, "o": int(ts(m["open_time"])), "c": int(ts(m["close_time"])),
                                "k": float(m["floor_strike"]), "y": m["result"] == "yes"})
        cursor = j.get("cursor")
        if not cursor: break
print(len(markets), "markets")


def kal(m):
    j = get(f"{K}/series/{m['s']}/markets/{m['t']}/candlesticks", {"start_ts": m["o"], "end_ts": m["c"], "period_interval": 1}) or {}
    rows = []
    for c in j.get("candlesticks", []) or []:
        rows.append([int(c["end_period_ts"]), dollars(c.get("yes_bid"), "close"), dollars(c.get("yes_ask"), "close"),
                     float(c.get("volume_fp", c.get("volume", 0)) or 0)])
    return m["t"], rows


kalshi, t0 = {}, time.time()
with ThreadPoolExecutor(max_workers=8) as ex:
    for i, (t, rows) in enumerate(ex.map(kal, markets)):
        kalshi[t] = rows
        if i % 1500 == 0: print(f"  kalshi {i}/{len(markets)} {time.time() - t0:.0f}s")


def cb(prod):
    d, t = {}, start - 3 * 3600
    while t < now - 60:
        t1 = min(t + 300 * 60, now)
        for c in get(f"{CB}/products/{prod}/candles", {"granularity": 60, "start": t, "end": t1}) or []:
            d[int(c[0])] = (float(c[3]), float(c[2]), float(c[1]), float(c[4]), float(c[5]))
        t = t1; time.sleep(0.1)
    return d


def bs(prod):
    d, t = {}, start - 3 * 3600
    while t < now - 60:
        t1 = min(t + 1000 * 60, now)
        j = get(f"https://www.bitstamp.net/api/v2/ohlc/{BS[prod]}/", {"step": 60, "limit": 1000, "start": t}) or {}
        for c in (j.get("data") or {}).get("ohlc", []):
            d[int(c["timestamp"])] = (float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"]), float(c["volume"]))
        t = t1; time.sleep(0.1)
    return d


price = {}
for s, prod in SERIES.items():
    a, b = cb(prod), bs(prod)
    comp = {}
    for m in set(a) | set(b):
        r = [x for x in (a.get(m), b.get(m)) if x]
        comp[m] = [round(sum(x[i] for x in r) / len(r), 4) for i in range(4)] + [round(sum(x[4] for x in r), 4)]
    price[s] = comp
    print(prod, "coinbase", len(a), "bitstamp", len(b), "composite", len(comp))

os.makedirs("research/data", exist_ok=True)
with gzip.open("research/data/history15m.json.gz", "wt") as f:
    json.dump({"generated": now, "days": DAYS, "markets": markets, "kalshi": kalshi,
               "price": {s: {str(k): v for k, v in d.items()} for s, d in price.items()}}, f, separators=(",", ":"))
print("saved", os.path.getsize("research/data/history15m.json.gz") // 1024, "KB")

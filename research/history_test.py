"""Test 15-minute crypto buys on a month of Kalshi's own minute-by-minute price history.

PUBLIC DATA ONLY (no account, keys or orders). For every settled KXBTC15M / KXETH15M / KXSOL15M market in the
last DAYS days: 1-minute candlesticks (YES bid / ask) from Kalshi, plus the result.

Each market contributes at most ONE trade per rule (the first minute the rule triggers), bought at the ask,
5 contracts, Kalshi taker fee. Writes research/history_test.json.
"""
import functools, json, math, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

print = functools.partial(print, flush=True)
K = "https://api.elections.kalshi.com/trade-api/v2"
UA = {"User-Agent": "kalshi-data-research/1.0"}
SERIES = ("KXBTC15M", "KXETH15M", "KXSOL15M")
DAYS = 30
C = 5
http = requests.Session()


def get(url, params=None, tries=4):
    for i in range(tries):
        try:
            r = http.get(url, params=params, headers=UA, timeout=10)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(1.5 * (i + 1)); continue
            if r.status_code >= 400:
                return {"_status": r.status_code}
            return r.json()
        except requests.RequestException:
            time.sleep(1.5 * (i + 1))
    return None


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def fee(p):
    return math.ceil(0.07 * C * p * (1 - p) * 100 - 1e-9) / 100


def num(d, key):
    """Kalshi returns either cents (int) or *_dollars strings; return dollars."""
    if d is None:
        return None
    if isinstance(d, dict):
        for k in (key + "_dollars", key):
            if d.get(k) not in (None, ""):
                v = float(d[k]); return v / 100 if k == key else v   # plain field = cents
    return None


now = time.time(); start = now - DAYS * 86400
markets = []
for s in SERIES:
    cursor = None
    for _ in range(80):
        p = {"series_ticker": s, "status": "settled", "limit": 1000, "min_close_ts": int(start), "max_close_ts": int(now)}
        if cursor: p["cursor"] = cursor
        j = get(f"{K}/markets", p) or {}
        for m in j.get("markets", []):
            if m.get("result") in ("yes", "no"):
                markets.append({"s": s, "ticker": m["ticker"], "open": ts(m["open_time"]), "close": ts(m["close_time"]),
                                "yes": m["result"] == "yes"})
        cursor = j.get("cursor")
        if not cursor: break
print(len(markets), "settled markets", {s: sum(m["s"] == s for m in markets) for s in SERIES})


def candles(m):
    j = get(f"{K}/series/{m['s']}/markets/{m['ticker']}/candlesticks",
            {"start_ts": int(m["open"]), "end_ts": int(m["close"]), "period_interval": 1})
    out = []
    for c in (j or {}).get("candlesticks", []) or []:
        bid = num((c.get("yes_bid") or {}), "close"); ask = num((c.get("yes_ask") or {}), "close")
        if bid is None or ask is None or not (0 < bid < ask < 1):
            continue
        out.append({"left": round((m["close"] - c["end_period_ts"]) / 60), "bid": bid, "ask": ask})
    return m, out, (j or {}).get("_status")


rows, statuses, t0 = [], {}, time.time()
with ThreadPoolExecutor(max_workers=6) as ex:
    for i, (m, cs, st) in enumerate(ex.map(candles, markets)):
        if st: statuses[st] = statuses.get(st, 0) + 1
        if cs: rows.append((m, cs))
        if i % 1000 == 0: print(f"  {i}/{len(markets)} markets, {len(rows)} with candles, {time.time() - t0:.0f}s, errors {statuses}")
print(len(rows), "markets with minute candles; errors", statuses)


def run(rule):
    """rule(candle, side_price, side_mid) -> bool. One trade per market and side, first trigger."""
    tr = []
    for m, cs in rows:
        for side in ("yes", "no"):
            for c in sorted(cs, key=lambda c: -c["left"]):
                price = c["ask"] if side == "yes" else 1 - c["bid"]
                mid = (c["bid"] + c["ask"]) / 2; mid = mid if side == "yes" else 1 - mid
                if rule(c, price, mid):
                    win = m["yes"] if side == "yes" else not m["yes"]
                    tr.append({"pnl": (C if win else 0) - C * price - fee(price), "win": win, "close": m["close"], "s": m["s"], "price": price})
                    break
    return tr


def summ(tr):
    if not tr: return None
    p = [t["pnl"] for t in tr]; n = len(p); mu = sum(p) / n
    sd = (sum((x - mu) ** 2 for x in p) / (n - 1)) ** 0.5 if n > 1 else 0
    weeks = {}
    for t in tr:
        w = int((t["close"] - start) // (7 * 86400)); weeks.setdefault(w, []).append(t["pnl"])
    return {"n": n, "win_%": round(100 * sum(t["win"] for t in tr) / n, 1), "avg_price_c": round(100 * sum(t["price"] for t in tr) / n, 1),
            "avg_pnl_$": round(mu, 3), "total_$": round(sum(p), 2),
            "ci95_avg_$": (round(mu - 1.96 * sd / n ** 0.5, 3), round(mu + 1.96 * sd / n ** 0.5, 3)),
            "by_week_avg_$": {f"week{w + 1}": round(sum(v) / len(v), 3) for w, v in sorted(weeks.items())},
            "by_coin_avg_$": {s: round(sum(t["pnl"] for t in tr if t["s"] == s) / max(1, sum(t["s"] == s for t in tr)), 3) for s in SERIES}}


out = {"days": DAYS, "markets": len(markets), "with_candles": len(rows), "tests": {}}
T = out["tests"]
T["chance 25-35%, 10-14 min left (the lead)"] = summ(run(lambda c, p, mid: 10 <= c["left"] <= 14 and 0.25 <= mid < 0.35))
T["chance 25-35%, 5-9 min left"] = summ(run(lambda c, p, mid: 5 <= c["left"] <= 9 and 0.25 <= mid < 0.35))
T["chance 25-35%, 1-4 min left"] = summ(run(lambda c, p, mid: 1 <= c["left"] <= 4 and 0.25 <= mid < 0.35))
for lo in range(5, 96, 10):
    T[f"chance {lo}-{lo + 10}%, 10-14 min left"] = summ(run(lambda c, p, mid, lo=lo: 10 <= c["left"] <= 14 and lo / 100 <= mid < (lo + 10) / 100))
for lo in range(5, 96, 10):
    T[f"chance {lo}-{lo + 10}%, any time"] = summ(run(lambda c, p, mid, lo=lo: lo / 100 <= mid < (lo + 10) / 100))
out["generated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
json.dump(out, open("research/history_test.json", "w"), indent=1)
for k, v in T.items():
    if v: print(f"{k:42s} n={v['n']:5d} win={v['win_%']:5.1f}% px={v['avg_price_c']:5.1f}c avg=${v['avg_pnl_$']:+.3f} CI{v['ci95_avg_$']} weeks {v['by_week_avg_$']}")

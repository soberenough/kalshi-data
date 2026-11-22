"""How do Kalshi's 15-minute crypto markets move around their target price?

PUBLIC DATA ONLY (no account, no keys, no orders):
  - Kalshi: every settled KXBTC15M / KXETH15M / KXSOL15M market in the window (target, open/close, result)
  - Coinbase Exchange: 1-minute candles for BTC-USD, ETH-USD, SOL-USD (a proxy for Kalshi's settlement index)
  - this repo's data branch: Kalshi order-book snapshots of those markets (to compare Kalshi's price with a model)

Questions:
  1. How is the target set? (target vs Coinbase price at the market's open)
  2. How often does the final price land above the target, by distance from target and minutes left?
  3. A simple model: P(finish above) = Phi( ln(spot/target) / (sigma * sqrt(minutes left)) ), sigma from the prior hour.
     Is it calibrated? Does it beat Kalshi's own price (Brier score) on the recorded snapshots?
  4. Where model and Kalshi disagree by >= 10c, what happened, after fees?
  5. Cheap contracts (ask <= 5c): how often did they win?
Writes research/target_moves.json and research/target_moves.md.
"""
import gzip, json, math, subprocess, time
from datetime import datetime, timezone, timedelta

import functools
import requests

print = functools.partial(print, flush=True)

K = "https://api.elections.kalshi.com/trade-api/v2"
CB = "https://api.exchange.coinbase.com"
UA = {"User-Agent": "kalshi-data-research/1.0"}
SERIES = {"KXBTC15M": "BTC-USD", "KXETH15M": "ETH-USD", "KXSOL15M": "SOL-USD"}
DAYS = 3


BS = {"BTC-USD": "btcusd", "ETH-USD": "ethusd", "SOL-USD": "solusd"}   # Bitstamp backup feed


def get(url, params=None, tries=5):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=10)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 * (i + 1)); continue
            r.raise_for_status(); return r.json()
        except requests.RequestException:
            time.sleep(2 * (i + 1))
    return None


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def fee_cents(p):  # Kalshi taker fee per contract, rounded up to the cent (0.07 * P * (1-P))
    return math.ceil(7 * p * (1 - p) / 100 * 100 - 1e-9) if 0 < p < 1 else 0


# ---- 1. settled markets ------------------------------------------------------------------------
now = time.time(); start = now - DAYS * 86400
markets = []
for s in SERIES:
    cursor = None
    for _ in range(40):
        p = {"series_ticker": s, "status": "settled", "limit": 1000, "min_close_ts": int(start), "max_close_ts": int(now)}
        if cursor: p["cursor"] = cursor
        j = get(f"{K}/markets", p) or {}
        for m in j.get("markets", []):
            if m.get("result") in ("yes", "no") and m.get("floor_strike") is not None:
                markets.append({"ticker": m["ticker"], "series": s, "target": float(m["floor_strike"]),
                                "open": ts(m["open_time"]), "close": ts(m["close_time"]), "result": m["result"],
                                "exp_value": m.get("expiration_value")})
        cursor = j.get("cursor")
        if not cursor: break
print(len(markets), "settled markets", {x: sum(m["series"] == x for m in markets) for x in SERIES})

# ---- 2. 1-minute prices: Coinbase, falling back to Bitstamp ---------------------------------------
px, source = {}, {}
for s, prod in SERIES.items():
    d = {}
    t0 = int(start) - 2 * 3600
    use_cb = False   # Bitstamp: 1000 one-minute bars per call, fast; Coinbase's ranged candle calls stalled from Actions
    calls = 0
    while t0 < int(now) - 60:
        if use_cb:
            t1 = min(t0 + 300 * 60, int(now))
            j = get(f"{CB}/products/{prod}/candles", {"granularity": 60,
                    "start": datetime.fromtimestamp(t0, timezone.utc).isoformat(),
                    "end": datetime.fromtimestamp(t1, timezone.utc).isoformat()}, tries=2)
            for c in j or []:
                d[int(c[0])] = float(c[4])
        else:
            t1 = min(t0 + 1000 * 60, int(now))
            j = get(f"https://www.bitstamp.net/api/v2/ohlc/{BS[prod]}/", {"step": 60, "limit": 1000, "start": t0}, tries=2) or {}
            for c in (j.get("data") or {}).get("ohlc", []):
                d[int(c["timestamp"])] = float(c["close"])
        t0 = t1; time.sleep(0.15); calls += 1
        if calls % 3 == 0: print(f"  {prod}: {calls} calls, {len(d)} minutes", flush=True)
    px[s] = d; source[s] = "coinbase" if use_cb else "bitstamp"
    print(prod, len(d), "minutes from", source[s])


def spot(s, t):
    """Coinbase close of the last full minute before t."""
    m = int(t // 60 * 60) - 60
    for k in range(5):
        v = px[s].get(m - 60 * k)
        if v: return v
    return None


def sigma(s, t):
    """Std dev of 1-minute log returns over the hour before t."""
    v = [px[s].get(int(t // 60 * 60) - 60 * k) for k in range(61)]
    v = [x for x in v if x]
    r = [math.log(a / b) for a, b in zip(v, v[1:])]
    return (sum(x * x for x in r) / len(r)) ** 0.5 if len(r) > 20 else None


def model_p(s, t, target, close):
    S, sg = spot(s, t), sigma(s, t)
    mins = (close - t) / 60
    if not S or not sg or mins <= 0: return None
    return phi(math.log(S / target) / (sg * math.sqrt(mins)))


# ---- 3. target rule, settlement proxy, calibration -------------------------------------------------
out = {"window_days": DAYS, "markets": len(markets), "price_source": source, "by_series": {}}
for s in SERIES:
    M = [m for m in markets if m["series"] == s]
    gaps, agree, rows = [], [], []
    for m in M:
        o = spot(s, m["open"] + 60); c = spot(s, m["close"] + 60)
        if o: gaps.append((m["target"] - o) / o * 1e4)            # bp: target vs Coinbase at open
        if c: agree.append((c >= m["target"]) == (m["result"] == "yes"))
        for mins_left in (14, 10, 7, 5, 3, 2, 1):
            t = m["close"] - mins_left * 60
            p = model_p(s, t, m["target"], m["close"])
            if p is not None:
                rows.append((mins_left, p, m["result"] == "yes"))
    cal = {}
    for lo in range(0, 100, 10):
        b = [y for _, p, y in rows if lo <= p * 100 < lo + 10]
        if len(b) >= 20: cal[f"{lo}-{lo+10}"] = {"n": len(b), "model_mid": lo + 5, "won_%": round(100 * sum(b) / len(b), 1)}
    by_left = {}
    for ml in (14, 10, 7, 5, 3, 2, 1):
        b = [(p, y) for m_, p, y in rows if m_ == ml]
        if b:
            by_left[ml] = {"n": len(b), "brier": round(sum((p - y) ** 2 for p, y in b) / len(b), 4),
                           "decided_%": round(100 * sum(1 for p, _ in b if p < .1 or p > .9) / len(b), 1)}
    gaps.sort()
    out["by_series"][s] = {
        "markets": len(M), "yes_%": round(100 * sum(m["result"] == "yes" for m in M) / max(len(M), 1), 1),
        "target_minus_open_bp": {"median": round(gaps[len(gaps) // 2], 2) if gaps else None,
                                 "p10": round(gaps[len(gaps) // 10], 2) if gaps else None,
                                 "p90": round(gaps[9 * len(gaps) // 10], 2) if gaps else None},
        "coinbase_agrees_with_settlement_%": round(100 * sum(agree) / max(len(agree), 1), 1),
        "model_calibration": cal, "by_minutes_left": by_left}

# ---- 4/5. recorded Kalshi snapshots: model vs market, disagreements, cheap contracts -----------------
subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", "+refs/heads/data:refs/remotes/origin/data"], check=True)
files = [f for f in subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "origin/data"], text=True).split()
         if "/orderbooks/" in f]
byt = {m["ticker"]: m for m in markets}
snaps = []
for f in files:
    for line in gzip.decompress(subprocess.check_output(["git", "show", f"origin/data:{f}"])).decode().splitlines():
        r = json.loads(line)
        if r.get("series") not in SERIES or r["ticker"] not in byt: continue
        try: bid, ask = float(r["yes_bid"]), float(r["yes_ask"])
        except (TypeError, ValueError): continue
        m = byt[r["ticker"]]
        p = model_p(m["series"], r["t"], m["target"], m["close"])
        if p is None or not (0 < bid < ask < 1): continue
        snaps.append({"s": m["series"], "mins": (m["close"] - r["t"]) / 60, "bid": bid, "ask": ask,
                      "mid": (bid + ask) / 2, "model": p, "yes": m["result"] == "yes"})
print(len(snaps), "matched snapshots")
if snaps:
    n = len(snaps)
    out["snapshots"] = {"n": n,
        "brier_kalshi_mid": round(sum((x["mid"] - x["yes"]) ** 2 for x in snaps) / n, 4),
        "brier_model": round(sum((x["model"] - x["yes"]) ** 2 for x in snaps) / n, 4)}
    trades = []
    for x in snaps:   # buy the side the model prefers at the ask, if it disagrees with Kalshi by >= 10c
        if x["model"] - x["ask"] >= 0.10:
            cost = x["ask"]; win = x["yes"]
        elif (1 - x["model"]) - (1 - x["bid"]) >= 0.10:
            cost = 1 - x["bid"]; win = not x["yes"]
        else:
            continue
        trades.append((1 if win else 0) - cost - fee_cents(cost) / 100)
    out["disagree_10c"] = {"trades": len(trades), "avg_pnl_per_contract_$": round(sum(trades) / len(trades), 4) if trades else None,
                           "win_rate_%": round(100 * sum(t > 0 for t in trades) / len(trades), 1) if trades else None}
    cheap = {}
    for x in snaps:
        for side, price, won in (("yes", x["ask"], x["yes"]), ("no", 1 - x["bid"], not x["yes"])):
            if price <= 0.05:
                k = f"{round(price * 100)}c"
                c = cheap.setdefault(k, [0, 0]); c[0] += 1; c[1] += won
    out["cheap_contracts"] = {k: {"n": v[0], "won": v[1], "won_%": round(100 * v[1] / v[0], 2),
                                  "breakeven_%": float(k[:-1])} for k, v in sorted(cheap.items(), key=lambda kv: int(kv[0][:-1]))}
    out["snapshots_by_minutes_left"] = {}
    for lo, hi in ((10, 15), (5, 10), (2, 5), (0, 2)):
        b = [x for x in snaps if lo <= x["mins"] < hi]
        if b:
            out["snapshots_by_minutes_left"][f"{lo}-{hi}"] = {"n": len(b),
                "brier_kalshi": round(sum((x["mid"] - x["yes"]) ** 2 for x in b) / len(b), 4),
                "brier_model": round(sum((x["model"] - x["yes"]) ** 2 for x in b) / len(b), 4)}

out["generated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
json.dump(out, open("research/target_moves.json", "w"), indent=1)
lines = [f"# 15-minute crypto markets vs their target ({DAYS} days to {out['generated_utc']})", "",
         "Public data only. Bitstamp 1-minute closes are a proxy for Kalshi's settlement index.", ""]
for s, v in out["by_series"].items():
    lines.append(f"- **{s}**: {v['markets']} markets, YES won {v['yes_%']}%; target vs Coinbase at open median "
                 f"{v['target_minus_open_bp']['median']} bp; Coinbase agrees with settlement {v['coinbase_agrees_with_settlement_%']}%")
if "snapshots" in out:
    lines += ["", f"- Snapshots: {out['snapshots']}", f"- Model vs Kalshi disagree >= 10c: {out['disagree_10c']}",
              f"- Cheap contracts: {out['cheap_contracts']}"]
open("research/target_moves.md", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))

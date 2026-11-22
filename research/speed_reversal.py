"""Speed, time-left and reversals in Kalshi 15-minute crypto markets (offline analysis of history15m.json.gz).

Builds, for every market and every minute with 1..14 minutes left:
  d_bp   signed distance from target (+ = above, i.e. YES currently winning)
  sig    typical 1-minute move (std of 1-min log returns over the prior hour, bp)
  z      d_bp / (sig * sqrt(minutes left))     -> "how many typical moves away, for the time left"
  v3     speed over the last 3 minutes (bp/min), signed so + means moving TOWARD the target from the losing side
  volr   volume in the last 3 min vs the prior hour's per-minute average
  sr     support/resistance: is the target beyond the last hour's high (if price below) / low (if above)?
  round  is there a round number ($100 BTC / $5 ETH / $0.50 SOL) between price and target?
Then: speed tables, empirical reversal odds, a train (weeks 1-3) / test (weeks 4-5) entry test vs Kalshi's own odds.
"""
import gzip, json, math, sys
from collections import defaultdict

import numpy as np

src = sys.argv[1] if len(sys.argv) > 1 else "research/data/history15m.json.gz"
D = json.load(gzip.open(src, "rt"))
ROUND = {"KXBTC15M": 100.0, "KXETH15M": 5.0, "KXSOL15M": 0.5}
C = 5


def fee(p): return math.ceil(0.07 * C * p * (1 - p) * 100 - 1e-9) / 100


price = {s: {int(k): v for k, v in d.items()} for s, d in D["price"].items()}
rows = []
for m in D["markets"]:
    P = price[m["s"]]; kal = {r[0]: r for r in D["kalshi"].get(m["t"], [])}
    for L in range(1, 15):
        t = m["c"] - 60 * L
        bar = P.get(t - 60)
        if not bar: continue
        S = bar[3]
        hist = [P.get(t - 60 * j) for j in range(1, 62)]
        if sum(h is not None for h in hist) < 50: continue
        closes = [h[3] for h in hist if h]
        rets = [math.log(a / b) for a, b in zip(closes, closes[1:])]
        sig = (sum(r * r for r in rets) / len(rets)) ** 0.5 * 1e4
        if sig <= 0: continue
        d = math.log(S / m["k"]) * 1e4
        b3 = P.get(t - 60 * 4)
        if not b3: continue
        v3_raw = math.log(S / b3[3]) * 1e4 / 3                  # bp per minute, + = rising
        v3 = -v3_raw if d > 0 else v3_raw                       # + = moving toward the target
        vol3 = sum((P.get(t - 60 * j) or [0] * 5)[4] for j in range(1, 4)) / 3
        volh = sum(h[4] for h in hist if h) / max(1, sum(h is not None for h in hist))
        hi = max(h[1] for h in hist if h); lo = min(h[2] for h in hist if h)
        sr = (m["k"] > hi) if d < 0 else (m["k"] < lo)          # target sits beyond the last hour's range
        step = ROUND[m["s"]]
        rnd = math.floor(max(S, m["k"]) / step) * step > min(S, m["k"])
        k = kal.get(t)
        bid, ask = (k[1], k[2]) if k else (None, None)
        rows.append({"s": m["s"], "c": m["c"], "L": L, "d": d, "sig": sig, "z": d / (sig * math.sqrt(L)), "v3": v3,
                     "volr": vol3 / volh if volh > 0 else None, "sr": sr, "rnd": rnd, "y": m["y"],
                     "lead_yes": d > 0, "bid": bid, "ask": ask})
print(len(rows), "market-minutes;", len(D["markets"]), "markets")
out = {"markets": len(D["markets"]), "rows": len(rows)}

# ---- 1. speed: typical move per minute, by coin ------------------------------------------------------
sp = {}
for s in ROUND:
    sg = sorted(r["sig"] for r in rows if r["s"] == s and r["L"] == 14)
    sp[s] = {"median_1min_move_bp": round(sg[len(sg) // 2], 2), "p90_1min_move_bp": round(sg[9 * len(sg) // 10], 2)}
out["speed"] = sp

# ---- 2. reversal odds: P(the side currently behind ends up winning) by z and minutes left --------------
def behind_wins(r): return r["y"] != r["lead_yes"]
ZB = [0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 99]
LB = [(10, 14), (5, 9), (3, 4), (1, 2)]
rev = {}
for lo, hi in LB:
    for a, b in zip(ZB, ZB[1:]):
        g = [r for r in rows if lo <= r["L"] <= hi and a <= abs(r["z"]) < b]
        if len(g) >= 50:
            rev[f"{lo}-{hi}m |z| {a}-{b}"] = {"n": len(g), "reversal_%": round(100 * sum(map(behind_wins, g)) / len(g), 1),
                                              "normal_model_%": round(100 * (1 - 0.5 * (1 + math.erf(((a + b) / 2 if b < 50 else 2.5) / math.sqrt(2)))), 1)}
out["reversal"] = rev
# does speed toward the target help a reversal?
spd = {}
for lo, hi in LB:
    for a, b in ((0.25, 0.75), (0.75, 1.5)):
        g = [r for r in rows if lo <= r["L"] <= hi and a <= abs(r["z"]) < b]
        for name, f in (("moving toward", lambda r: r["v3"] > 0.5 * r["sig"]), ("flat", lambda r: abs(r["v3"]) <= 0.5 * r["sig"]),
                        ("moving away", lambda r: r["v3"] < -0.5 * r["sig"])):
            gg = [r for r in g if f(r)]
            if len(gg) >= 40:
                spd[f"{lo}-{hi}m |z| {a}-{b} {name}"] = {"n": len(gg), "reversal_%": round(100 * sum(map(behind_wins, gg)) / len(gg), 1)}
out["reversal_by_speed"] = spd
for key, f in (("volume surge (>2x)", lambda r: r["volr"] and r["volr"] > 2), ("normal volume", lambda r: r["volr"] and r["volr"] <= 2),
               ("target beyond last hour's range", lambda r: r["sr"]), ("target inside last hour's range", lambda r: not r["sr"]),
               ("round number in between", lambda r: r["rnd"]), ("no round number in between", lambda r: not r["rnd"])):
    g = [r for r in rows if 3 <= r["L"] <= 9 and 0.25 <= abs(r["z"]) < 1.5 and f(r)]
    out.setdefault("reversal_by_context", {})[key] = {"n": len(g), "reversal_%": round(100 * sum(map(behind_wins, g)) / len(g), 1) if g else None}

# ---- 3. train (first 3 weeks) / test (rest): logistic model on the features vs Kalshi's odds ------------
t_split = min(m["c"] for m in D["markets"]) + 21 * 86400
def feats(r):
    vr = min(r["volr"] or 1, 5)
    zt = max(min(r["z"], 4), -4)
    sgn = 1 if r["d"] > 0 else -1
    return [1, zt, zt ** 3 / 10, sgn * r["v3"] / r["sig"], sgn * (r["v3"] / r["sig"]) * (r["L"] / 14), sgn * math.log(vr),
            sgn * (1 if r["sr"] else 0), sgn * (1 if r["rnd"] else 0), 1 / math.sqrt(r["L"])]
tr = [r for r in rows if r["c"] < t_split]; te = [r for r in rows if r["c"] >= t_split and r["ask"] and r["bid"] and 0 < r["bid"] < r["ask"] < 1]
X = np.array([feats(r) for r in tr]); Y = np.array([1.0 if r["y"] else 0.0 for r in tr])
w = np.zeros(X.shape[1])
for _ in range(3000):
    p = 1 / (1 + np.exp(-X @ w)); w -= 0.5 * X.T @ (p - Y) / len(Y) + 1e-4 * w
Xt = np.array([feats(r) for r in te]); pt = 1 / (1 + np.exp(-Xt @ w)); yt = np.array([1.0 if r["y"] else 0.0 for r in te])
mid = np.array([(r["bid"] + r["ask"]) / 2 for r in te])
out["test"] = {"train_rows": len(tr), "test_rows": len(te), "weights": [round(x, 3) for x in w],
               "brier_model": round(float(np.mean((pt - yt) ** 2)), 4), "brier_kalshi": round(float(np.mean((mid - yt) ** 2)), 4)}
# trade: one entry per market per side, first minute the model beats Kalshi's ask by >= edge
for edge in (0.05, 0.10, 0.15):
    seen, pnl = set(), []
    for r, p in sorted(zip(te, pt), key=lambda x: (x[0]["c"], -x[0]["L"])):
        for side, price, prob, win in (("yes", r["ask"], p, r["y"]), ("no", 1 - r["bid"], 1 - p, not r["y"])):
            key = (r["c"], r["s"], side)
            if key in seen or not (0.05 <= price <= 0.95): continue
            if prob - price >= edge:
                seen.add(key); pnl.append((C if win else 0) - C * price - fee(price))
    if pnl:
        a = np.array(pnl)
        out["test"][f"trades_edge_{int(edge * 100)}c"] = {"n": len(a), "win_%": round(100 * float(np.mean(a > 0)), 1),
            "avg_$": round(float(a.mean()), 3), "total_$": round(float(a.sum()), 2),
            "ci95": [round(float(a.mean() - 1.96 * a.std(ddof=1) / len(a) ** 0.5), 3), round(float(a.mean() + 1.96 * a.std(ddof=1) / len(a) ** 0.5), 3)]}
json.dump(out, open("research/speed_reversal.json", "w"), indent=1)
print(json.dumps(out, indent=1)[:6000])

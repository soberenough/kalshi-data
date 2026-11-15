"""Kalshi liquidity-reward tracker (PUBLIC DATA ONLY: no account, no keys, no orders).

Kalshi's Liquidity Incentive Program pays a fixed pool per market for resting orders near the best
price, sampled once per second (help.kalshi.com/incentive-programs/liquidity-incentive-program):
  - Target Size per side; the Reference Price is where cumulative depth from the best price reaches
    Target/5; orders at or better get full credit, worse ones are discounted by
    discount_factor ** ticks_away.
  - A snapshot counts only if BOTH sides have at least Target Size resting.
  - Our score per snapshot = our yes-side share + our no-side share; payout share = score / 2.

Every run (about every 10 minutes) this records, for the best-paying active programs, what a
hypothetical order of SIZE contracts at the best bid on each side would earn, how much capital it
ties up, and the market's cumulative volume (so later runs can estimate how often it would fill).
Output: data/rewards/YYYY-MM-DD/HHMM.jsonl.gz on the data branch.
"""
import argparse
import gzip
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://api.elections.kalshi.com/trade-api/v2"
UA = {"User-Agent": "starship-bridge-recorder/1.0"}
SIZE = 100
TOP = 250


def get(url, params=None, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=20)
        except requests.RequestException:
            time.sleep(1.5 * (i + 1))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(1.5 * (i + 1))
            continue
        r.raise_for_status()
        return r.json()
    return None


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def programs():
    out, cursor = [], None
    for _ in range(50):
        p = {"limit": 1000, "status": "active"}
        if cursor:
            p["cursor"] = cursor
        j = get(f"{API}/incentive_programs", p) or {}
        out += j.get("incentive_programs", [])
        cursor = j.get("next_cursor") or j.get("cursor")
        if not cursor:
            break
    now = time.time()
    return [p for p in out if p.get("incentive_type") == "liquidity" and ts(p["start_date"]) <= now < ts(p["end_date"])]


def per_day(p):
    days = max((ts(p["end_date"]) - ts(p["start_date"])) / 86400, 1 / 24)
    return p["period_reward"] / 1e4 / days


def side(levels, target, df):
    lv = sorted(([float(a), float(b)] for a, b in (levels or [])), key=lambda x: -x[0])
    total = sum(s for _, s in lv)
    if not lv or total < target:
        return {"ok": False, "best": lv[0][0] if lv else None, "depth": total, "q": None}
    cum, ref = 0.0, lv[0][0]
    for pr, s in lv:
        cum += s
        if cum >= target / 5:
            ref = pr
            break
    q = c2 = 0.0
    for pr, s in lv:
        if c2 >= target:
            break
        q += s * df ** max(0, round((ref - pr) * 100))
        c2 += s
    return {"ok": True, "best": lv[0][0], "depth": total, "q": q}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    progs = sorted(programs(), key=per_day, reverse=True)[:TOP]
    recs = []
    for p in progs:
        ob = (get(f"{API}/markets/{p['market_ticker']}/orderbook") or {}).get("orderbook_fp") or {}
        m = (get(f"{API}/markets/{p['market_ticker']}") or {}).get("market") or {}
        time.sleep(0.05)
        T, df = float(p["target_size_fp"]), p["discount_factor_bps"] / 1e4
        y, n = side(ob.get("yes_dollars"), T, df), side(ob.get("no_dollars"), T, df)
        both = y["ok"] and n["ok"]
        share = ((SIZE / (y["q"] + SIZE)) + (SIZE / (n["q"] + SIZE))) / 2 if both else 0.0
        cap = SIZE * ((y["best"] or 0) + (n["best"] or 0))
        recs.append({"t": int(time.time()), "ticker": p["market_ticker"], "series": p["series_ticker"],
                     "per_day": round(per_day(p), 2), "target": T, "df": df, "end": p["end_date"],
                     "yes_best": y["best"], "no_best": n["best"], "yes_depth": y["depth"], "no_depth": n["depth"],
                     "both_sides_qualify": both, "our_share": round(share, 4),
                     "est_per_day": round(per_day(p) * share, 2), "capital": round(cap, 2),
                     "volume": m.get("volume_fp"), "oi": m.get("open_interest_fp"), "close": m.get("close_time")})
    d = Path(a.out) / "data" / "rewards" / now.strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    with gzip.open(d / f"{now:%H%M}.jsonl.gz", "wt") as f:
        for r in recs:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    q = [r for r in recs if r["both_sides_qualify"]]
    print(f"{now:%H:%M} UTC: {len(recs)} programs, {len(q)} two-sided; est ${sum(r['est_per_day'] for r in q):.0f}/day "
          f"on ${sum(r['capital'] for r in q):.0f} posted")


if __name__ == "__main__":
    main()

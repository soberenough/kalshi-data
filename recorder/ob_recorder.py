"""Kalshi order-book recorder (PUBLIC DATA ONLY: no account, no keys, no orders).

Every run snapshots the live order book (top 15 price levels per side, with sizes), volume,
open interest and last price for every open market in the target series, and appends one
gzipped JSON-lines file per run under data/orderbooks/YYYY-MM-DD/. Run every ~10 minutes,
this gives the exact book history that hourly candles can't: real depth for fill simulation,
when prices move, and how fast the market reacts to outside data.

  python relay/ob_recorder.py --out /path/to/data-branch
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
LEVELS = 15
SERIES = [
    # crypto 15-min and hourly
    "KXBTC15M", "KXETH15M", "KXSOL15M", "KXBTCD",
    # gas (AAA)
    "KXAAAGASD", "KXAAAGASW", "KXAAAGASDFL", "KXAAAGASDOH", "KXAAAGASDIL", "KXAAAGASDNJ", "KXAAAGASDCA",
    "KXAAAGASDNC", "KXAAAGASDMI", "KXAAAGASDTX", "KXAAAGASDNY", "KXAAAGASDGA",
    # weather
    "KXHIGHNY", "KXHIGHCHI", "KXHIGHLAX", "KXHIGHMIA", "KXHIGHAUS", "KXHIGHDEN", "KXHIGHPHIL",
    "KXHIGHTATL", "KXHIGHTPHX", "KXHIGHTSEA", "KXHIGHTDAL", "KXHIGHTDC", "KXHIGHTMIN", "KXHIGHTHOU",
    "KXHIGHTLV", "KXHIGHTSFO", "KXHIGHTBOS", "KXLOWTNYC", "KXRAIN",
    # other slow / retail-heavy
    "KXSPOTIFYD", "KXSPOTIFYGLOBALD", "KXTSAW", "KXTXERCOTPEAKD", "KXTOPSONG",
]


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


def levels(side):
    """Kalshi returns [[price, size], ...] ascending; keep the best (highest) LEVELS."""
    rows = [[float(p), float(s)] for p, s in (side or [])]
    return sorted(rows, key=lambda x: -x[0])[:LEVELS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    recs, errors = [], 0
    for s in SERIES:
        j = get(f"{API}/markets", {"series_ticker": s, "status": "open", "limit": 200})
        if not j:
            errors += 1
            continue
        for m in j.get("markets", []):
            ob = get(f"{API}/markets/{m['ticker']}/orderbook")
            time.sleep(0.05)
            book = (ob or {}).get("orderbook_fp") or {}
            recs.append({
                "t": int(time.time()), "series": s, "ticker": m["ticker"], "event": m.get("event_ticker"),
                "close": m.get("close_time"), "floor": m.get("floor_strike"), "cap": m.get("cap_strike"),
                "strike_type": m.get("strike_type"),
                "yes_bid": m.get("yes_bid_dollars"), "yes_ask": m.get("yes_ask_dollars"),
                "last": m.get("last_price_dollars"), "volume": m.get("volume_fp"), "oi": m.get("open_interest_fp"),
                "yes_book": levels(book.get("yes_dollars")), "no_book": levels(book.get("no_dollars")),
            })
            if ob is None:
                errors += 1
    d = Path(a.out) / "data" / "orderbooks" / now.strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    with gzip.open(d / f"{now:%H%M}.jsonl.gz", "wt") as f:
        for r in recs:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    print(f"{now:%Y-%m-%d %H:%M} UTC: {len(recs)} markets recorded, {errors} errors")


if __name__ == "__main__":
    main()

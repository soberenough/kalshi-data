"""One request to each public source used by target_moves.py, with timing. Writes research/probe_sources.json."""
import json, time, requests
UA = {"User-Agent": "kalshi-data-research/1.0"}
now = int(time.time()); out = {}
tests = {
 "kalshi_settled_btc15m": ("https://api.elections.kalshi.com/trade-api/v2/markets", {"series_ticker": "KXBTC15M", "status": "settled", "limit": 5, "min_close_ts": now - 86400}),
 "kalshi_series_btc15m_any": ("https://api.elections.kalshi.com/trade-api/v2/markets", {"series_ticker": "KXBTC15M", "limit": 3}),
 "coinbase_candles": ("https://api.exchange.coinbase.com/products/BTC-USD/candles", {"granularity": 60}),
 "bitstamp_ohlc": ("https://www.bitstamp.net/api/v2/ohlc/btcusd/", {"step": 60, "limit": 5}),
 "kraken_ohlc": ("https://api.kraken.com/0/public/OHLC", {"pair": "XBTUSD", "interval": 1}),
}
for k, (u, p) in tests.items():
    t = time.time()
    try:
        r = requests.get(u, params=p, headers=UA, timeout=15)
        body = r.text[:600]
        out[k] = {"status": r.status_code, "secs": round(time.time() - t, 2), "sample": body}
    except Exception as e:
        out[k] = {"error": str(e)[:200], "secs": round(time.time() - t, 2)}
    print(k, out[k].get("status"), out[k]["secs"], flush=True)
json.dump(out, open("research/probe_sources.json", "w"), indent=1)

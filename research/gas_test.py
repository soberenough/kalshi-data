"""Kalshi daily AAA gas markets (KXAAAGASD): can a simple momentum model beat the market price?

Market: "national average regular gas > $X on day D (AAA)". Opens D-1 ~8 AM ET, closes midnight ET.
Decision time: D-1 at 9 PM ET (AAA's D-1 number is long published by then).
Model (walk-forward, no look-ahead): change_D ~ Normal(k * mean(last 3 daily changes), sigma),
k and sigma fit on the previous 30 days only. P(YES) = P(AAA_D > strike).
Trade rule: take the market (taker fee, quadratic) when model edge > fee + 2 cents.
Reports Brier (model vs market mid) and P&L per contract in two halves (both must be positive to count).
Also tries Yahoo for RBOB futures (RB=F) to see if a wholesale signal is reachable.
"""
import json, math, os, statistics, time, datetime as dt, requests
HOUR = int(os.environ.get("DEC_HOUR", "21"))
B = "https://api.elections.kalshi.com/trade-api/v2"
S = "KXAAAGASD"
OUT = f"research/gas_test_results_{os.environ.get('DEC_HOUR','21')}h.md"


def get(url, **p):
    for i in range(4):
        try:
            r = requests.get(url, params=p, timeout=60)
            if r.status_code == 429:
                time.sleep(2 + i * 2); continue
            return r.json()
        except Exception:
            time.sleep(2)
    return {}


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def fee(p):  # taker, per contract, dollars
    return math.ceil(0.07 * p * (1 - p) * 100 - 1e-9) / 100


def dollars(c, side):
    v = c.get(side) or {}
    for k in ("close_dollars", "close"):
        if v.get(k) not in (None, ""):
            x = float(v[k]); return x / 100 if x > 1.5 else x
    return None


# 1. all settled markets
mk, cur = [], None
while True:
    p = {"series_ticker": S, "status": "settled", "limit": 1000}
    if cur: p["cursor"] = cur
    j = get(f"{B}/markets", **p); mk += j.get("markets", []); cur = j.get("cursor")
    if not cur: break

def day_of(m):  # event date D from close time (04:59Z on D = midnight ET start of D... close is end of D-1 ET)
    ct = dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
    return (ct - dt.timedelta(hours=5)).date() + dt.timedelta(days=1) if ct.hour < 12 else ct.date()

aaa = {}
for m in mk:
    try: aaa[day_of(m)] = float(m["expiration_value"])
    except (TypeError, ValueError): pass
days = sorted(aaa)
chg = {d: aaa[d] - aaa[days[i - 1]] for i, d in enumerate(days) if i and (d - days[i - 1]).days == 1}

# 2. model probability per market + market price at D-1 21:00 ET
rows = []
for m in mk:
    D = day_of(m)
    prev = [D - dt.timedelta(days=i) for i in range(1, 34)]
    if not all(x in aaa for x in prev[:4]): continue
    hist = [chg[x] for x in prev[1:31] if x in chg and (x - dt.timedelta(days=3)) in chg]
    # fit k, sigma on last 30 days: predictor = mean of the 3 changes before each day
    xs, ys = [], []
    for x in prev[1:31]:
        lag = [x - dt.timedelta(days=i) for i in (1, 2, 3)]
        if x in chg and all(l in chg for l in lag):
            xs.append(sum(chg[l] for l in lag) / 3); ys.append(chg[x])
    if len(xs) < 15: continue
    sxx = sum(a * a for a in xs) or 1e-9
    k = sum(a * b for a, b in zip(xs, ys)) / sxx
    sig = statistics.pstdev([b - k * a for a, b in zip(xs, ys)]) or 0.002
    lagD = [D - dt.timedelta(days=i) for i in (1, 2, 3)]
    if not all(l in chg for l in lagD): continue
    mu = aaa[D - dt.timedelta(days=1)] + k * sum(chg[l] for l in lagD) / 3
    strike = m.get("floor_strike")
    if strike is None: continue
    p_yes = 1 - ncdf((float(strike) - mu) / sig)
    t_dec = int(dt.datetime.combine(D - dt.timedelta(days=1), dt.time(HOUR, 0)).replace(tzinfo=dt.timezone(dt.timedelta(hours=-5))).timestamp())
    c = get(f"{B}/series/{S}/markets/{m['ticker']}/candlesticks", start_ts=t_dec - 6 * 3600, end_ts=t_dec, period_interval=60)
    cs = [x for x in c.get("candlesticks", []) if x.get("end_period_ts", 0) <= t_dec]
    if not cs: continue
    bid, ask = dollars(cs[-1], "yes_bid"), dollars(cs[-1], "yes_ask")
    if bid is None or ask is None or ask <= 0 or bid >= 1: continue
    y = 1 if m.get("result") == "yes" else 0
    rows.append(dict(D=D.isoformat(), t=m["ticker"], p=p_yes, bid=bid, ask=ask, y=y))
    time.sleep(0.05)

# 3. score
def score(rs):
    if not rs: return dict(n=0)
    mid = [(r["bid"] + r["ask"]) / 2 for r in rs]
    bm = sum((r["p"] - r["y"]) ** 2 for r in rs) / len(rs)
    bk = sum((mm - r["y"]) ** 2 for mm, r in zip(mid, rs)) / len(rs)
    pnl = []
    for r in rs:
        if r["p"] - r["ask"] > fee(r["ask"]) + 0.02 and r["ask"] < 0.99:
            pnl.append(r["y"] - r["ask"] - fee(r["ask"]))
        elif (r["bid"] - r["p"]) > fee(1 - r["bid"]) + 0.02 and r["bid"] > 0.01:
            pnl.append((1 - r["y"]) - (1 - r["bid"]) - fee(1 - r["bid"]))
    tt = (statistics.mean(pnl) / (statistics.pstdev(pnl) / math.sqrt(len(pnl)))) if len(pnl) > 2 and statistics.pstdev(pnl) > 0 else 0
    return dict(n=len(rs), brier_model=round(bm, 4), brier_market=round(bk, 4), trades=len(pnl),
                pnl_per_contract_c=round(100 * statistics.mean(pnl), 2) if pnl else 0, total_c=round(100 * sum(pnl), 1), t=round(tt, 2))

rows.sort(key=lambda r: r["D"])
half = len(rows) // 2
res = {"all": score(rows), "first_half": score(rows[:half]), "second_half": score(rows[half:])}

# 4. RBOB reachability
try:
    yj = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/RB=F", params={"range": "6mo", "interval": "1d"},
                      headers={"User-Agent": "Mozilla/5.0"}, timeout=30).json()
    q = yj["chart"]["result"][0]; rbob = f"reachable: {len(q['timestamp'])} daily closes"
except Exception as e:
    rbob = f"not reachable ({type(e).__name__})"

with open(OUT, "w") as f:
    f.write(f"# Kalshi daily gas (KXAAAGASD) momentum test, decision {HOUR}:00 ET D-1, run {dt.datetime.utcnow():%Y-%m-%d %H:%MZ}\n\n")
    f.write(f"Settled markets: {len(mk)}; AAA days: {len(days)} ({days[0] if days else ''} to {days[-1] if days else ''}); priced rows: {len(rows)}\n\n")
    for k_, v in res.items(): f.write(f"- **{k_}**: {json.dumps(v)}\n")
    f.write(f"\nRBOB (Yahoo RB=F): {rbob}\n\nPass bar: model Brier below market in both halves AND positive P&L per contract in both halves with t > 2.\n")
print(open(OUT).read())

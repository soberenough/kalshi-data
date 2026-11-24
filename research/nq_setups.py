"""Backtest three popular NQ day-trading setups on Nasdaq futures 5-minute bars, traded as 1 MNQ.

Setups (regular session 09:30-16:00 ET only, flat by 15:55):
  fvg          bullish gap: low[i] > high[i-2]; buy a pullback to the gap top within 12 bars,
               stop 1 tick below the gap bottom, target 2R. Bearish mirror.
  ifvg         a gap that price CLOSES through flips direction: a broken bullish gap becomes resistance;
               sell a retest of the gap bottom within 12 bars, stop 1 tick above the gap top, 2R. Mirror.
  orb_retest   09:30-10:00 opening range; a close outside the range, then a bar that retests the
               broken edge and closes back outside -> enter at that close, stop past the retest
               bar's extreme, target 2R. One trade per day.

Costs per MNQ round trip: $1.50 commissions/fees; 1 tick slippage on market entries and stop exits.
Limit entries need price to trade 1 tick THROUGH the level. If a bar touches both stop and target,
the stop is assumed first. Only results are saved (no raw price data).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ET = ZoneInfo("America/New_York")
TICK, PT_USD, FEES = 0.25, 2.0, 1.50
OUT = Path(__file__).resolve().parent


def fetch(interval="5m", rng="60d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/NQ=F?interval={interval}&range={rng}"
    for i in range(5):
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        if r.status_code == 200:
            break
        time.sleep(3 * (i + 1))
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    bars = []
    for t, o, h, l, c in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"]):
        if None in (o, h, l, c):
            continue
        dt = datetime.fromtimestamp(t, timezone.utc).astimezone(ET)
        if (dt.hour, dt.minute) >= (9, 30) and (dt.hour, dt.minute) < (16, 0) and dt.weekday() < 5:
            bars.append({"t": dt, "o": o, "h": h, "l": l, "c": c})
    return bars


def by_day(bars):
    days = {}
    for b in bars:
        days.setdefault(b["t"].date(), []).append(b)
    return [v for _, v in sorted(days.items()) if len(v) >= 60]


def run_trade(day, k, side, entry, stop, target, market_entry):
    """Walk bars k.. ; returns (exit_price, reason). Entry assumed filled at `entry` at bar k (close if market)."""
    for b in day[k + (1 if market_entry else 0):]:
        if (b["t"].hour, b["t"].minute) >= (15, 55):
            return b["o"], "eod"
        hit_stop = b["l"] <= stop if side == 1 else b["h"] >= stop
        hit_tgt = b["h"] >= target if side == 1 else b["l"] <= target
        if hit_stop:
            return stop - side * TICK, "stop"           # slippage on stop
        if hit_tgt:
            return target, "target"
    return day[-1]["c"], "eod"


def pnl_usd(side, entry, exit_, market_entry):
    slip = TICK if market_entry else 0.0
    pts = side * (exit_ - entry) - slip
    return pts * PT_USD - FEES


def fvg_trades(day, inverse=False):
    trades, busy_until = [], -1
    for i in range(2, len(day) - 2):
        if i <= busy_until:
            continue
        a, c = day[i - 2], day[i]
        for side, top, bot in ((1, c["l"], a["h"]), (-1, a["l"], c["h"])):
            if top - bot < 2 * TICK:            # ignore tiny gaps
                continue
            # bullish gap (side 1): zone [bot, top]; bearish gap (side -1): zone [bot=c.h, top=a.l]
            for j in range(i + 1, min(i + 13, len(day))):
                b = day[j]
                if (b["t"].hour, b["t"].minute) >= (15, 30):
                    break
                if not inverse:
                    level = top if side == 1 else bot
                    touched = b["l"] <= level - TICK if side == 1 else b["h"] >= level + TICK
                    if touched:
                        stop = (bot - TICK) if side == 1 else (top + TICK)
                        risk = abs(level - stop)
                        tgt = level + side * 2 * risk
                        # same-bar stop check
                        if (side == 1 and b["l"] <= stop) or (side == -1 and b["h"] >= stop):
                            ex, why = stop - side * TICK, "stop"
                        else:
                            ex, why = run_trade(day, j, side, level, stop, tgt, True)
                        trades.append({"d": str(b["t"].date()), "side": side, "usd": pnl_usd(side, level, ex, False), "why": why})
                        busy_until = j
                        break
                else:
                    broke = b["c"] < bot if side == 1 else b["c"] > top
                    if broke:
                        s2 = -side                               # flipped direction
                        level = bot if side == 1 else top        # broken edge, now the retest level
                        for k in range(j + 1, min(j + 13, len(day))):
                            bb = day[k]
                            if (bb["t"].hour, bb["t"].minute) >= (15, 30):
                                break
                            touched = bb["h"] >= level + TICK if s2 == -1 else bb["l"] <= level - TICK
                            if touched:
                                stop = (top + TICK) if s2 == -1 else (bot - TICK)
                                risk = abs(stop - level)
                                tgt = level + s2 * 2 * risk
                                if (s2 == -1 and bb["h"] >= stop) or (s2 == 1 and bb["l"] <= stop):
                                    ex, why = stop - s2 * TICK, "stop"
                                else:
                                    ex, why = run_trade(day, k, s2, level, stop, tgt, True)
                                trades.append({"d": str(bb["t"].date()), "side": s2, "usd": pnl_usd(s2, level, ex, False), "why": why})
                                busy_until = k
                                break
                        break
            if busy_until >= i:
                break
    return trades


def orb_trades(day):
    rng = [b for b in day if (b["t"].hour, b["t"].minute) < (10, 0)]
    if len(rng) < 6:
        return []
    hi, lo = max(b["h"] for b in rng), min(b["l"] for b in rng)
    broke = 0
    for k, b in enumerate(day):
        if (b["t"].hour, b["t"].minute) < (10, 0):
            continue
        if (b["t"].hour, b["t"].minute) >= (15, 0):
            break
        if not broke:
            broke = 1 if b["c"] > hi else -1 if b["c"] < lo else 0
            continue
        edge = hi if broke == 1 else lo
        retest = (b["l"] <= edge + TICK and b["c"] > edge) if broke == 1 else (b["h"] >= edge - TICK and b["c"] < edge)
        if retest:
            entry = b["c"]
            stop = (b["l"] - TICK) if broke == 1 else (b["h"] + TICK)
            risk = abs(entry - stop)
            if risk < 2 * TICK:
                return []
            ex, why = run_trade(day, k, broke, entry, stop, entry + broke * 2 * risk, True)
            return [{"d": str(b["t"].date()), "side": broke, "usd": pnl_usd(broke, entry, ex, True), "why": why}]
    return []


def stats(tr):
    if not tr:
        return {"trades": 0}
    eq, peak, mdd, tot = 0.0, 0.0, 0.0, 0.0
    for t in tr:
        eq += t["usd"]; peak = max(peak, eq); mdd = max(mdd, peak - eq)
    wins = [t["usd"] for t in tr if t["usd"] > 0]
    losses = [-t["usd"] for t in tr if t["usd"] <= 0]
    half = len(tr) // 2
    return {"trades": len(tr), "win_pct": round(100 * len(wins) / len(tr), 1),
            "total_usd": round(eq, 2), "per_trade_usd": round(eq / len(tr), 2),
            "max_drawdown_usd": round(mdd, 2),
            "profit_factor": round(sum(wins) / sum(losses), 2) if losses and sum(losses) else None,
            "first_half_usd": round(sum(t["usd"] for t in tr[:half]), 2),
            "second_half_usd": round(sum(t["usd"] for t in tr[half:]), 2),
            "exits": {k: sum(1 for t in tr if t["why"] == k) for k in ("target", "stop", "eod")}}


def main():
    bars = fetch()
    days = by_day(bars)
    res = {"data": f"NQ=F 5-minute bars, RTH, {days[0][0]['t'].date()} to {days[-1][0]['t'].date()}, {len(days)} days",
           "costs": "1 MNQ ($2/pt), $1.50 round-trip fees, 1 tick slippage on market entries and stops",
           "results": {}}
    for name, fn in (("fvg", lambda d: fvg_trades(d)), ("ifvg", lambda d: fvg_trades(d, inverse=True)),
                     ("orb_retest", orb_trades)):
        tr = [t for d in days for t in fn(d)]
        res["results"][name] = stats(tr)
    (OUT / "nq_setups_results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()

"""ChatGPT's (Science Officer) NQ plans #2 and #3 from starship-bridge Issue #1 (2026-11-24), coded as specified.
Walk-forward: train on the prior 3 weeks (choose params by net PnL / max drawdown), test the next 2 weeks, roll by 2 weeks.

Interpretations where the spec was open (stated so they can be challenged):
 #2 ORB retest v2
  - OR = 09:30-09:45 (three 5-min bars). Breakout = a bar CLOSES >= OR high + c ticks (short mirror).
  - "retest window +-w ticks" = buy limit at OR high + w ticks (sell limit at OR low - w ticks); filled when
    a later bar trades at/through the limit between 09:45 and 11:30. One trade/day; skip if OR range < 0.2% of price.
  - Stop = OR mid. Target = R x risk. Stop moves to entry once price reaches +0.5R. Time exit 12:00 at bar open.
  - Same bar hitting stop and target: stop first. Limit fill: no slippage. Stop: 1 tick slippage. $1.50 RT.
 #3 Gap fade
  - Prior close = last RTH bar close of the previous day; gap = today 09:30 open - prior close.
  - ATR = ATR(20) of 5-min bars at 09:30 (the spec says "ATR20 on 5-min"; "ATR(overnight)" read as the same).
  - Trigger: |gap| >= g x ATR and the 09:30-09:45 bar closes against the gap by >= k x ATR (gap up: close <= open - k*ATR).
  - Entry: limit at the midpoint of that 15-min bar (a 50% retrace toward the gap side), valid 09:45-11:30.
  - Stop: beyond the 15-min bar's extreme by s% of price. Target: 50% gap fill (open - 0.5*gap). Skip if entry is
    already past the target. Time exit 11:30. No trades on FOMC decision days.
"""
from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

from nq_setups import ET, FEES, PT_USD, TICK, fetch  # noqa: F401

OUT = Path(__file__).resolve().parent
FOMC = {"2026-09-16", "2026-10-28", "2026-12-09"}


def hm(b):
    return (b["t"].hour, b["t"].minute)


def days_all(bars):
    d = {}
    for b in bars:
        d.setdefault(b["t"].date(), []).append(b)
    return [v for _, v in sorted(d.items()) if len(v) >= 60]


def walk(day, start_idx, side, entry, stop, target, be_at, t_exit, stop_slip=True):
    """Manage an open trade from bar start_idx (inclusive). Returns exit price, reason."""
    moved = False
    for b in day[start_idx:]:
        if hm(b) >= t_exit:
            return b["o"], "time"
        cur_stop = entry if moved else stop
        hit_s = b["l"] <= cur_stop if side == 1 else b["h"] >= cur_stop
        hit_t = b["h"] >= target if side == 1 else b["l"] <= target
        if hit_s:
            return cur_stop - side * (TICK if stop_slip else 0), ("be" if moved else "stop")
        if hit_t:
            return target, "target"
        if be_at is not None and ((side == 1 and b["h"] >= be_at) or (side == -1 and b["l"] <= be_at)):
            moved = True
    return day[-1]["c"], "eod"


def usd(side, entry, exit_):
    return side * (exit_ - entry) * PT_USD - FEES


# ---------------- plan 2 ----------------
def orb2(day, c_ticks, w_ticks, R):
    orb = [b for b in day if hm(b) < (9, 45)]
    if len(orb) < 3:
        return None
    hi, lo = max(b["h"] for b in orb), min(b["l"] for b in orb)
    if (hi - lo) / lo < 0.002:
        return None
    mid = (hi + lo) / 2
    side = 0
    for i, b in enumerate(day):
        if hm(b) < (9, 45):
            continue
        if hm(b) >= (11, 30):
            return None
        if not side:
            if b["c"] >= hi + c_ticks * TICK:
                side = 1
            elif b["c"] <= lo - c_ticks * TICK:
                side = -1
            continue
        limit = hi + w_ticks * TICK if side == 1 else lo - w_ticks * TICK
        if (side == 1 and b["l"] <= limit) or (side == -1 and b["h"] >= limit):
            risk = abs(limit - mid)
            if risk < 2 * TICK:
                return None
            tgt = limit + side * R * risk
            be = limit + side * 0.5 * risk
            # same-bar stop
            if (side == 1 and b["l"] <= mid) or (side == -1 and b["h"] >= mid):
                ex, why = mid - side * TICK, "stop"
            else:
                ex, why = walk(day, i + 1, side, limit, mid, tgt, be, (12, 0))
            return {"d": str(b["t"].date()), "usd": usd(side, limit, ex), "why": why}
    return None


# ---------------- plan 3 ----------------
def atr20(prev_bars):
    trs = []
    for a, b in zip(prev_bars[:-1], prev_bars[1:]):
        trs.append(max(b["h"] - b["l"], abs(b["h"] - a["c"]), abs(b["l"] - a["c"])))
    return sum(trs[-20:]) / min(20, len(trs)) if trs else None


def gapfade(day, prev_day, g, k, s_pct):
    if str(day[0]["t"].date()) in FOMC or not prev_day:
        return None
    pc = prev_day[-1]["c"]
    op = day[0]["o"]
    gap = op - pc
    atr = atr20(prev_day[-21:])
    if not atr or abs(gap) < g * atr:
        return None
    first = [b for b in day if hm(b) < (9, 45)]
    if len(first) < 3:
        return None
    fh, fl, fc = max(b["h"] for b in first), min(b["l"] for b in first), first[-1]["c"]
    side = -1 if gap > 0 else 1                      # fade the gap
    against = (op - fc) if gap > 0 else (fc - op)
    if against < k * atr:
        return None
    entry = (op + fc) / 2
    stop = fh * (1 + s_pct) if side == -1 else fl * (1 - s_pct)
    tgt = op - 0.5 * gap
    if (side == -1 and entry <= tgt) or (side == 1 and entry >= tgt):
        return None
    for i, b in enumerate(day):
        if hm(b) < (9, 45):
            continue
        if hm(b) >= (11, 30):
            return None
        if (side == -1 and b["h"] >= entry) or (side == 1 and b["l"] <= entry):
            if (side == -1 and b["h"] >= stop) or (side == 1 and b["l"] <= stop):
                ex, why = stop - side * TICK, "stop"
            else:
                ex, why = walk(day, i + 1, side, entry, stop, tgt, None, (11, 30))
            return {"d": str(b["t"].date()), "usd": usd(side, entry, ex), "why": why}
    return None


# ---------------- evaluation ----------------
def mdd(trs):
    eq = peak = dd = 0.0
    for t in trs:
        eq += t["usd"]; peak = max(peak, eq); dd = max(dd, peak - eq)
    return dd


def score(trs):
    net = sum(t["usd"] for t in trs)
    if not trs:
        return -1e9
    return net / max(mdd(trs), 1.0)


def summary(trs):
    if not trs:
        return {"trades": 0}
    wins = [t["usd"] for t in trs if t["usd"] > 0]
    losses = [-t["usd"] for t in trs if t["usd"] <= 0]
    half = len(trs) // 2
    by_day = {}
    for t in trs:
        by_day[t["d"]] = by_day.get(t["d"], 0) + t["usd"]
    vals = list(by_day.values())
    mean = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals)) if len(vals) > 1 else 0
    return {"trades": len(trs), "win_pct": round(100 * len(wins) / len(trs), 1),
            "net_usd": round(sum(t["usd"] for t in trs), 2),
            "profit_factor": round(sum(wins) / sum(losses), 2) if sum(losses) else None,
            "max_dd_usd": round(mdd(trs), 2),
            "avg_winner_usd": round(sum(wins) / len(wins), 2) if wins else 0,
            "first_half_usd": round(sum(t["usd"] for t in trs[:half]), 2),
            "second_half_usd": round(sum(t["usd"] for t in trs[half:]), 2),
            "sharpe_daily_ann": round(mean / sd * math.sqrt(252), 2) if sd else None}


def walk_forward(days, fn, grid, needs_prev):
    weeks = {}
    for i, d in enumerate(days):
        weeks.setdefault(d[0]["t"].isocalendar()[:2], []).append(i)
    wk = list(weeks.values())
    oos, log = [], []
    w = 3
    while w < len(wk):
        train_idx = [i for x in wk[w - 3:w] for i in x]
        test_weeks = wk[w:w + 2]
        test_idx = [i for x in test_weeks for i in x]

        def run(params, idx):
            out = []
            for i in idx:
                r = fn(days[i], days[i - 1] if i else None, *params) if needs_prev else fn(days[i], *params)
                if r:
                    out.append(r)
            return out
        best = max(grid, key=lambda p: score(run(p, train_idx)))
        test = run(best, test_idx)
        for t_w in test_weeks:
            tw = run(best, t_w)
            log.append({"week_start": str(days[t_w[0]][0]["t"].date()), "params": best,
                        "trades": len(tw), "net_usd": round(sum(t["usd"] for t in tw), 2)})
        oos += test
        w += 2
    return oos, log


def main():
    days = days_all(fetch())
    res = {"data": f"NQ=F 5-min RTH {days[0][0]['t'].date()}..{days[-1][0]['t'].date()} ({len(days)} days)",
           "spec": "ChatGPT plans #2 and #3, starship-bridge Issue #1, 2026-11-24; interpretations in the script docstring"}
    g2 = list(itertools.product([1, 2, 3], [0, 1, 2], [1.25, 1.5, 1.75, 2.0]))
    oos2, log2 = walk_forward(days, orb2, g2, False)
    s2 = summary(oos2)
    pos_weeks = sum(1 for x in log2 if x["net_usd"] > 0)
    s2["pass"] = {"min_80_trades": s2.get("trades", 0) >= 80, "pf_1.2": (s2.get("profit_factor") or 0) >= 1.2,
                  "dd_le_1.5x_avg_winner": s2.get("max_dd_usd", 1e9) <= 1.5 * s2.get("avg_winner_usd", 0),
                  "both_halves_pos": s2.get("first_half_usd", -1) > 0 and s2.get("second_half_usd", -1) > 0,
                  "3of4_weeks_pos": pos_weeks / max(len(log2), 1) >= 0.75}
    res["plan2_orb_retest_v2"] = {"oos": s2, "weeks": log2}
    g3 = list(itertools.product([0.5, 0.6, 0.7], [0.2, 0.3, 0.4], [0.001, 0.0015, 0.002]))
    oos3, log3 = walk_forward(days, gapfade, g3, True)
    s3 = summary(oos3)
    s3["pass"] = {"min_25_trades": s3.get("trades", 0) >= 25, "pf_1.25": (s3.get("profit_factor") or 0) >= 1.25,
                  "sharpe_0.8": (s3.get("sharpe_daily_ann") or 0) >= 0.8, "dd_le_500": s3.get("max_dd_usd", 1e9) <= 500,
                  "both_halves_pos": s3.get("first_half_usd", -1) > 0 and s3.get("second_half_usd", -1) > 0}
    res["plan3_gap_fade"] = {"oos": s3, "weeks": log3}
    # full-sample (in-sample) counts for context
    res["context_all_days_trade_counts"] = {
        "plan2_any_params_max": max(sum(1 for d in days if orb2(d, *p)) for p in g2),
        "plan3_any_params_max": max(sum(1 for i, d in enumerate(days) if i and gapfade(d, days[i - 1], *p)) for p in g3)}
    (OUT / "chatgpt_nq_plans_results.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()

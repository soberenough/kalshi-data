# Gold evening breakdown backtest

Backtest: evening-session short on a break of BOTH the day's RTH low and the overnight low (gold futures).
Rule (as proposed after the 2026-11-17 drop):
  For each trading day D: L = min(RTH low of D [09:30-16:00 ET], overnight low [D-1 18:00 .. D 09:30 ET]).
  Evening window: D 18:00 -> D+1 02:00 ET (configurable). First time price trades below L - 0.1, sell 1 at L - 0.1.
  Stop = entry + STOP pts. Target = entry - TGT pts (or none). Otherwise exit at window end (close of last bar).
  Same bar touches stop and target -> assume STOP (worst case). Costs: 0.5 pt per round trip (commission + 1 tick slip each way).
Controls: mirror LONG on break of max(RTH high, overnight high); and the same short rule during RTH next day is not tested.
Data: Yahoo Finance GC=F (full-size gold; MGC moves identically, $10/pt for MGC).


## 15m bars (4589)
| variant | n | win% | avg pt | total $ (1 MGC) | max DD $ |
|---|---|---|---|---|---|
| short stop40 tgtNone until02:00 | 20 | 55 | 0.5 | 100 | 1300 |
| short stop40 tgtNone until09:00 | 24 | 58 | 6.57 | 1577 | 1852 |
| short stop40 tgt100 until02:00 | 20 | 55 | 0.5 | 100 | 1300 |
| short stop40 tgt100 until09:00 | 24 | 58 | 6.46 | 1550 | 1852 |
| short stop20 tgt40 until02:00 | 20 | 50 | -2.32 | -464 | 1101 |
| short stop20 tgt40 until09:00 | 24 | 42 | 0.19 | 46 | 1105 |
| short stop15 tgt30 until02:00 | 20 | 35 | -2.94 | -588 | 1037 |
| short stop15 tgt30 until09:00 | 24 | 38 | -1.04 | -250 | 1100 |
| short stop10 tgt20 until02:00 | 20 | 20 | -4.5 | -900 | 1095 |
| short stop10 tgt20 until09:00 | 24 | 21 | -4.25 | -1020 | 1410 |
| long stop40 tgtNone until02:00 | 10 | 40 | 5.88 | 588 | 979 |
| long stop40 tgtNone until09:00 | 17 | 47 | 4.37 | 743 | 1147 |
| long stop40 tgt100 until02:00 | 10 | 40 | 5.88 | 588 | 979 |
| long stop40 tgt100 until09:00 | 17 | 47 | 4.37 | 743 | 1147 |
| long stop20 tgt40 until02:00 | 10 | 40 | 5.57 | 557 | 632 |
| long stop20 tgt40 until09:00 | 17 | 35 | 0.05 | 9 | 822 |
| long stop15 tgt30 until02:00 | 10 | 40 | 3.18 | 318 | 482 |
| long stop15 tgt30 until09:00 | 17 | 24 | -2.86 | -486 | 1061 |
| long stop10 tgt20 until02:00 | 10 | 30 | -1.5 | -150 | 630 |
| long stop10 tgt20 until09:00 | 17 | 18 | -4.35 | -739 | 1024 |
## 60m bars (13678)
| variant | n | win% | avg pt | total $ (1 MGC) | max DD $ |
|---|---|---|---|---|---|
| short stop40 tgtNone until02:00 | 143 | 39 | -5.53 | -7909 | 9269 |
| short stop40 tgtNone until09:00 | 199 | 34 | -6.29 | -12523 | 15822 |
| short stop40 tgt100 until02:00 | 143 | 40 | -5.0 | -7151 | 8511 |
| short stop40 tgt100 until09:00 | 199 | 35 | -4.82 | -9601 | 12900 |
| short stop20 tgt40 until02:00 | 143 | 31 | -4.67 | -6671 | 7199 |
| short stop20 tgt40 until09:00 | 199 | 27 | -5.29 | -10525 | 11874 |
| short stop15 tgt30 until02:00 | 143 | 24 | -5.59 | -7993 | 8424 |
| short stop15 tgt30 until09:00 | 199 | 22 | -6.1 | -12131 | 12610 |
| short stop10 tgt20 until02:00 | 143 | 13 | -6.58 | -9403 | 9543 |
| short stop10 tgt20 until09:00 | 199 | 14 | -6.7 | -13336 | 13337 |
| long stop40 tgtNone until02:00 | 194 | 52 | 2.88 | 5583 | 1996 |
| long stop40 tgtNone until09:00 | 262 | 56 | 5.43 | 14232 | 2486 |
| long stop40 tgt100 until02:00 | 194 | 52 | 2.83 | 5488 | 1996 |
| long stop40 tgt100 until09:00 | 262 | 56 | 5.66 | 14820 | 2238 |
| long stop20 tgt40 until02:00 | 194 | 48 | 0.92 | 1781 | 2773 |
| long stop20 tgt40 until09:00 | 262 | 46 | 1.39 | 3650 | 4569 |
| long stop15 tgt30 until02:00 | 194 | 44 | -0.6 | -1163 | 3084 |
| long stop15 tgt30 until09:00 | 262 | 40 | -0.72 | -1892 | 5968 |
| long stop10 tgt20 until02:00 | 194 | 38 | -1.89 | -3669 | 4210 |
| long stop10 tgt20 until09:00 | 262 | 33 | -2.04 | -5344 | 6479 |
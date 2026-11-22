# 15-minute crypto markets vs their target (7 days to 2026-11-22T16:12:38+00:00)

Public data only. A Coinbase+Bitstamp composite (60-second averages, as Kalshi settles) is a proxy for Kalshi's settlement index.

- **KXBTC15M**: 664 markets, YES won 46.1%; our target is off by a median 0.78 bp; composite agrees with settlement 98.3% (using Kalshi's target) / 97.3% (using our own target)
- **KXETH15M**: 664 markets, YES won 49.5%; our target is off by a median 1.87 bp; composite agrees with settlement 95.9% (using Kalshi's target) / 97.1% (using our own target)
- **KXSOL15M**: 664 markets, YES won 49.2%; our target is off by a median 1.99 bp; composite agrees with settlement 97.6% (using Kalshi's target) / 97.6% (using our own target)

- Snapshots: {'n': 3153, 'brier_kalshi_mid': 0.1553, 'brier_model': 0.164}
- Model vs Kalshi disagree >= 10c: {'trades': 483, 'avg_pnl_per_contract_$': -0.0587, 'win_rate_%': 25.9}
- Cheap contracts: {'0c': {'n': 144, 'won': 1, 'won_%': 0.69, 'breakeven_%': 0.0}, '1c': {'n': 175, 'won': 1, 'won_%': 0.57, 'breakeven_%': 1.0}, '2c': {'n': 101, 'won': 1, 'won_%': 0.99, 'breakeven_%': 2.0}, '3c': {'n': 71, 'won': 1, 'won_%': 1.41, 'breakeven_%': 3.0}, '4c': {'n': 73, 'won': 4, 'won_%': 5.48, 'breakeven_%': 4.0}, '5c': {'n': 29, 'won': 2, 'won_%': 6.9, 'breakeven_%': 5.0}}

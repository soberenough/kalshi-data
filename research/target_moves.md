# 15-minute crypto markets vs their target (3 days to 2026-11-22T15:42:42+00:00)

Public data only. Bitstamp 1-minute closes are a proxy for Kalshi's settlement index.

- **KXBTC15M**: 288 markets, YES won 43.8%; target vs Coinbase at open median 1.69 bp; Coinbase agrees with settlement 87.5%
- **KXETH15M**: 288 markets, YES won 49.7%; target vs Coinbase at open median 3.86 bp; Coinbase agrees with settlement 89.9%
- **KXSOL15M**: 288 markets, YES won 48.3%; target vs Coinbase at open median 2.87 bp; Coinbase agrees with settlement 86.8%

- Snapshots: {'n': 1375, 'brier_kalshi_mid': 0.154, 'brier_model': 0.1623}
- Model vs Kalshi disagree >= 10c: {'trades': 210, 'avg_pnl_per_contract_$': 0.0, 'win_rate_%': 31.4}
- Cheap contracts: {'0c': {'n': 59, 'won': 0, 'won_%': 0.0, 'breakeven_%': 0.0}, '1c': {'n': 67, 'won': 0, 'won_%': 0.0, 'breakeven_%': 1.0}, '2c': {'n': 45, 'won': 0, 'won_%': 0.0, 'breakeven_%': 2.0}, '3c': {'n': 33, 'won': 1, 'won_%': 3.03, 'breakeven_%': 3.0}, '4c': {'n': 33, 'won': 3, 'won_%': 9.09, 'breakeven_%': 4.0}, '5c': {'n': 11, 'won': 2, 'won_%': 18.18, 'breakeven_%': 5.0}}

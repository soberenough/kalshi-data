# kalshi-data

Records **public** Kalshi market data for research: live order books (top 15 levels per side)
for ~600 markets, and Kalshi's Liquidity Incentive Program rewards with an estimate of what a
resting order at the best price would earn. Public API only: no account, no keys, no orders.

- Runs every hour on GitHub Actions (free for public repos); each run records six snapshots ~10 minutes apart.
- Data is written to the `data` branch: `data/orderbooks/YYYY-MM-DD/HHMM.jsonl.gz` and `data/rewards/YYYY-MM-DD/HHMM.jsonl.gz`.
- Research and decisions live in the private crew repo.

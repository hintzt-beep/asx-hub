# Status

## Completed
- Dashboard uses a wide layout with responsive padding (no max-width cap).
- Watchlist tab: add/remove tickers, BUY/HOLD/SELL per ticker (long-term signal), saved per user under the `watchlist` key in the store.
- Portfolio: Remove button on each Bought today card, plus Clear all test trades (asks to confirm). Both save to the `trades` key.
- Paper-trading bot (alerter.py): on each BUY setup it opens a pretend position in the `system`/`paper_account` store doc ($10,000 start). Size: 1% account risk at the stop (after fees and slippage), max 20% per position. $10 brokerage each way, 0.1% slippage against us on every fill. One paper buy per ticker per day, none while that ticker is open. Closes on stop or target (checked on 5-minute bars, stop wins ties, gaps fill at the open) and ASX day trades close 15 min before the close. Closed trades record entry, exit, shares, costs, P/L. No broker code, no real orders.
- Paper tab in the dashboard: account value vs start, total P/L, win rate, trades, open positions, last 20 trades.
- alerts workflow has a concurrency group so two runs can't both open the same position.
- Matrix-style re-skin (CSS and `.streamlit/config.toml` only): near-black background, neon green #00FF41 accent, dim green borders, monospace headings and numbers, green glow on the hero card and selected tab. BUY green, SELL red, HOLD amber unchanged. No logic or layout changes.

## Current task
None.

## Tests
- No automated test suite. Watchlist checked headlessly with Streamlit AppTest (stubbed store and price data): add, signal, remove, per-user save all pass. Same for trade remove, clear-all confirm/cancel/delete. Paper bot: `alerter.py --once` run against a fake Supabase and fake prices, plus rule tests (sizing, 20% cap, costs, stop/target/gap/ASX-close exits, duplicate guards, failed-load safety) and the Paper tab, all passing. Not run against real Supabase or live prices.

## Decisions
- Watchlist signal reuses `scan_long` / `long_word`, cached 15 minutes. Tickers without 200 days of data show HOLD with "No data".

## Next steps
- Paper bot: let it run for a few weeks before judging anything. Win rate on a few trades means little; this is not out-of-sample evidence.
- Paper account is in dollars for everything; crypto and ASX are not FX-converted. Gaps can lose more than the 1% planned.
- Trades have no test flag, so Clear all removes every trade (and frees pot cash). Add a flag if real and test trades must be separated.
- Run the app against real Supabase and live prices.

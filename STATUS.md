# Status

## Completed
- Dashboard uses a wide layout with responsive padding (no max-width cap).
- Watchlist tab: add/remove tickers, BUY/HOLD/SELL per ticker (long-term signal), saved per user under the `watchlist` key in the store.

## Current task
None.

## Tests
- No automated test suite. Watchlist checked headlessly with Streamlit AppTest (stubbed store and price data): add, signal, remove, per-user save all pass.

## Decisions
- Watchlist signal reuses `scan_long` / `long_word`, cached 15 minutes. Tickers without 200 days of data show HOLD with "No data".

## Next steps
- Run the app against real Supabase and live prices.

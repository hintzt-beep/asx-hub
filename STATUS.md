# Status

## Completed
- Dashboard uses a wide layout with responsive padding (no max-width cap).
- Watchlist tab: add/remove tickers, BUY/HOLD/SELL per ticker (long-term signal), saved per user under the `watchlist` key in the store.
- Portfolio: Remove button on each Bought today card, plus Clear all test trades (asks to confirm). Both save to the `trades` key.

## Current task
None.

## Tests
- No automated test suite. Watchlist checked headlessly with Streamlit AppTest (stubbed store and price data): add, signal, remove, per-user save all pass. Same for trade remove, clear-all confirm/cancel/delete.

## Decisions
- Watchlist signal reuses `scan_long` / `long_word`, cached 15 minutes. Tickers without 200 days of data show HOLD with "No data".

## Next steps
- Trades have no test flag, so Clear all removes every trade (and frees pot cash). Add a flag if real and test trades must be separated.
- Run the app against real Supabase and live prices.

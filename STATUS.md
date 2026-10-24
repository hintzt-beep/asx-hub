# Status

## Completed
- Dashboard uses a wide layout with responsive padding (no max-width cap).
- Watchlist tab: add/remove tickers, BUY/HOLD/SELL per ticker (long-term signal), saved per user under the `watchlist` key in the store.
- Portfolio: Remove button on each Bought today card, plus Clear all test trades (asks to confirm). Both save to the `trades` key.
- Paper-trading bot (alerter.py): on each BUY setup it opens a pretend position in the `system`/`paper_account` store doc ($10,000 start). Size: 1% account risk at the stop (after fees and slippage), max 20% per position. $10 brokerage each way, 0.1% slippage against us on every fill. One paper buy per ticker per day, none while that ticker is open. Closes on stop or target (checked on 5-minute bars, stop wins ties, gaps fill at the open) and ASX day trades close 15 min before the close. Closed trades record entry, exit, shares, costs, P/L. No broker code, no real orders.
- Paper tab in the dashboard: account value vs start, total P/L, win rate, trades, open positions, last 20 trades.
- alerts workflow has a concurrency group so two runs can't both open the same position.
- Dark mechanical re-skin (replaces the Matrix look; CSS, `.streamlit/config.toml` and hero markup only): #0A0A0C background, steel-grey #3A3F47 borders, blood-red #C1121F accent with soft red glow on hero, tabs and buttons, chrome-grey secondary text, Orbitron headings (Google Fonts), monospace numbers. App name IRONPAW and an inline-SVG robot bear (one glowing red eye) on the login and Home hero cards. BUY green, HOLD amber, SELL red (#EF4444, brighter than the accent) unchanged. No logic changes.
- Old ntfy alerts are off (`OLD_ALERTS = False` in alerter.py; code kept). Every paper-bot action now pushes to Ty's topic only: each buy, each sell (stop loss, target hit, end-of-day close) and each skipped or rejected buy (once per ticker and reason per day, so repeats don't spam).
- Shadow bot (paper only): every alerter run it reads Ty's real holdings (qty, paid, bought) and never writes them. Rules in `shadow.py`: SELL when the trend is SELL and the gain after the $10 sell brokerage is over 2%, or when the loss is worse than 8% whatever the trend; otherwise HOLD with a plain reason (notes >12 months held: Australian tax discount). On a SELL it logs a paper sale at the current price (`system`/`shadow_log`: ticker, price, date, reason, costs; each holding sold at most once), then paper-buys the highest-scoring BUY on the Long term list with the proceeds (less $10 brokerage and 0.1% slippage). If no BUY idea exists the proceeds wait and are invested when one appears. Every shadow move pushes to Ty's topic.
- Portfolio: holding cards show paid, now, gain/loss in $ and %, BUY/HOLD/SELL and the reason; add form takes what you paid and the buy date; new Shadow bot section (paper sales and buys, how each is doing since, total paper P/L, total brokerage).

- Home "Needs you" now lists the latest 6 paper-bot and shadow-bot actions (buys, sells, stops, targets, end-of-day closes) with their plain-English reason and Melbourne time, newest first, or "All quiet." The trend-only SELL alerts for holdings and logged trades are gone from Home (holding cards on Portfolio still show their own view).

## Current task
None.

## Tests
- No automated test suite. Watchlist checked headlessly with Streamlit AppTest (stubbed store and price data): add, signal, remove, per-user save all pass. Same for trade remove, clear-all confirm/cancel/delete. Paper bot: `alerter.py --once` run against a fake Supabase and fake prices, plus rule tests (sizing, 20% cap, costs, stop/target/gap/ASX-close exits, duplicate guards, failed-load safety) and the Paper tab, all passing. Notifications: unit-tested for every action type, plus a real `alerter.py --once` run with ntfy calls recorded (3 pushes, all to Ty). Shadow bot: real `alerter.py --once` against a fake Supabase and prices (sells, buys, ntfy to Ty only, no duplicates on a second run, holdings unchanged), threshold and edge-case tests, dashboard cards and section. Not run against real Supabase, real ntfy or live prices.

## Decisions
- Watchlist signal reuses `scan_long` / `long_word`, cached 15 minutes. Tickers without 200 days of data show HOLD with "No data".

## Next steps
- Existing holdings have no `paid` yet: the shadow bot ignores them until they are removed and re-added with a price paid (and buy date for the 12-month note).
- Shadow sale is logged at the current price with $10 brokerage and no slippage (matches the gain formula); the paper buy has 0.1% slippage.
- Paper bot: let it run for a few weeks before judging anything. Win rate on a few trades means little; this is not out-of-sample evidence.
- Paper account is in dollars for everything; crypto and ASX are not FX-converted. Gaps can lose more than the 1% planned.
- Trades have no test flag, so Clear all removes every trade (and frees pot cash). Add a flag if real and test trades must be separated.
- Run the app against real Supabase and live prices.

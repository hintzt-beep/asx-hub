# Status

## Completed
- Dashboard uses a wide layout with responsive padding (no max-width cap).
- Watchlist tab: add tickers, BUY/HOLD/SELL per ticker (long-term signal), saved per user under the `watchlist` key in the store.
- Portfolio: Clear all test trades (asks to confirm) saves to the `trades` key.
- alerts workflow has a concurrency group so two runs can't both open the same position.
- Dark mechanical re-skin (replaces the Matrix look; CSS, `.streamlit/config.toml` and hero markup only): #0A0A0C background, steel-grey #3A3F47 borders, blood-red #C1121F accent with soft red glow on hero, tabs and buttons, chrome-grey secondary text, Orbitron headings (Google Fonts), monospace numbers. App name IRONPAW and an inline-SVG robot bear (one glowing red eye) on the login and Home hero cards. BUY green, HOLD amber, SELL red (#EF4444, brighter than the accent) unchanged. No logic changes.
- Old ntfy alerts are off (`OLD_ALERTS = False` in alerter.py; code kept). Bot actions push to Ty's topic via `notify_ty`.
- Shadow bot (paper only): every alerter run it reads Ty's real holdings (qty, paid, bought) and never writes them. Rules in `shadow.py`: SELL when the trend is SELL and the gain after the $10 sell brokerage is over 2%, or when the loss is worse than 8% whatever the trend; otherwise HOLD with a plain reason (notes >12 months held: Australian tax discount). On a SELL it logs a paper sale at the current price (`system`/`shadow_log`: ticker, price, date, reason, costs; each holding sold at most once), then paper-buys the highest-scoring BUY on the Long term list with the proceeds (less $10 brokerage and 0.1% slippage). If no BUY idea exists the proceeds wait and are invested when one appears. Every shadow move pushes to Ty's topic.
- Portfolio: holding cards show paid, now, gain/loss in $ and %, BUY/HOLD/SELL and the reason; add form takes what you paid and the buy date; new Shadow bot section (paper sales and buys, how each is doing since, total paper P/L, total brokerage).

- One login: a single Admin user (password from `TY_PASSWORD`). Nathan's login is removed. Admin's data still lives under the `Ty` owner key in Supabase so nothing needed migrating; Nathan's saved data is left in Supabase untouched.
- Race step 1 (cleanup): removed the Remove buttons on holdings and Bought today, the Home bot-moves section, and the old single paper bot and its Paper tab (its saved `system/paper_account` data is left in Supabase, unused). Shadow bot stays on Portfolio.
- Race step 2 (`race.py`, hooked into `alerter.py`): a STOCKS race (the 30 ASX names, trades only while the ASX is open and prices are fresh) with 5 bots plus a Buy and Hold racer (all-in VAS.AX on day one, never trades). Each racer starts each 3-week season with $50,000. Shared rules: $10 brokerage per stock trade, 0.1% slippage on every fill, max 25% per position, a stop on every position, one buy per ticker per day and never while holding it, loss brake benches a bot at -15% until the reset. Season end: results to `hall_of_fame`, best bot gets the champion badge, accounts reset, final standings pushed. Pings: every trade (default) or one daily summary after 5pm Melbourne (`race_settings.pings`). The CRYPTO race is built (0.1% fee, BTC-USD benchmark) but switched off: ASX only for now (`ENABLED` in race.py). Bot strategies come in step 3.

## Current task
Bot race, step 3 of 5 next: the five bots' trading identities, reasons and diaries.

## Tests
- No automated test suite. Watchlist checked headlessly with Streamlit AppTest (stubbed store and price data): add, signal, remove, per-user save all pass. Same for trade remove, clear-all confirm/cancel/delete. Paper bot: `alerter.py --once` run against a fake Supabase and fake prices, plus rule tests (sizing, 20% cap, costs, stop/target/gap/ASX-close exits, duplicate guards, failed-load safety) and the Paper tab, all passing. Notifications: unit-tested for every action type, plus a real `alerter.py --once` run with ntfy calls recorded (3 pushes, all to Ty). Shadow bot: real `alerter.py --once` against a fake Supabase and prices (sells, buys, ntfy to Ty only, no duplicates on a second run, holdings unchanged), threshold and edge-case tests, dashboard cards and section. Race engine: real `alerter.py --once` against a fake Supabase (race created, no trading while the ASX is closed) plus rule tests with a controlled clock (benchmark, fees, slippage, 25% cap, stop rule, duplicate guard, risk sizing, stop/target/trailing on 5-minute bars, holiday skip, loss brake, season end and reset, ping modes, Supabase-down safety). Not run against real Supabase, real ntfy or live prices.

## Decisions
- Watchlist signal reuses `scan_long` / `long_word`, cached 15 minutes. Tickers without 200 days of data show HOLD with "No data".

## Next steps
- Existing holdings have no `paid` yet: the shadow bot ignores them until they are removed and re-added with a price paid (and buy date for the 12-month note).
- Shadow sale is logged at the current price with $10 brokerage and no slippage (matches the gain formula); the paper buy has 0.1% slippage.
- Paper bot: let it run for a few weeks before judging anything. Win rate on a few trades means little; this is not out-of-sample evidence.
- Paper account is in dollars for everything; crypto and ASX are not FX-converted. Gaps can lose more than the 1% planned.
- Trades have no test flag, so Clear all removes every trade (and frees pot cash). Add a flag if real and test trades must be separated.
- Run the app against real Supabase and live prices.

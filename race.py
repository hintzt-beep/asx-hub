"""Bot race: five paper-trading bots and a Buy and Hold benchmark, in a STOCKS race and a CRYPTO race.

Pretend money only. No real orders, ever. Prices come only from yfinance; a ticker with no data is skipped,
never filled in. Everything is stored in Supabase under owner "system".
"""
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from store import get, put

MEL = ZoneInfo("Australia/Melbourne")
START_CASH = 50000.0
SEASON_DAYS = 21
SLIP = 0.001                       # 0.1% against us on every fill
STOCK_FEE = 10.0                   # brokerage per stock trade
CRYPTO_FEE = 0.001                 # 0.1% of the trade value per crypto trade
MAX_POS = 0.25                     # max 25% of a bot's account in one position
LOSS_BRAKE = 0.15                  # down 15% in a season: benched until the reset
HISTORY_EVERY = timedelta(minutes=30)
FRESH = timedelta(minutes=30)      # stocks race only trades on bars this recent (skips holidays)
SUMMARY_HOUR = 17                  # daily summary push, Melbourne time

STOCKS = ["ALL.AX", "ANZ.AX", "BHP.AX", "BOE.AX", "CBA.AX", "COL.AX", "CSL.AX", "EVN.AX", "FMG.AX", "GMG.AX",
          "IGO.AX", "LYC.AX", "MIN.AX", "MQG.AX", "NAB.AX", "NST.AX", "PDN.AX", "PLS.AX", "QBE.AX", "REA.AX",
          "RIO.AX", "STO.AX", "TCL.AX", "TLS.AX", "WBC.AX", "WDS.AX", "WES.AX", "WOW.AX", "WTC.AX", "XRO.AX"]
CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD", "ADA-USD", "DOGE-USD", "AVAX-USD",
          "LINK-USD", "DOT-USD", "LTC-USD", "BCH-USD"]
BOTS = ["Tyler", "Ryan", "Nathan", "Newton", "Morpheus"]
BENCH = "Buy and Hold"
ALL_RACES = {"stocks": {"key": "stocks", "name": "STOCKS", "doc": "race_stocks", "tickers": STOCKS, "bench": "VAS.AX", "crypto": False},
             "crypto": {"key": "crypto", "name": "CRYPTO", "doc": "race_crypto", "tickers": CRYPTO, "bench": "BTC-USD", "crypto": True}}
ENABLED = ["stocks"]               # ASX only for now; add "crypto" to switch the 24/7 crypto race on
RACES = {k: ALL_RACES[k] for k in ENABLED}
STRATEGIES = {}                    # bot name -> strategy object with .trade(); filled in by bots.py


def p(x):
    return f"{x:,.2f}" if x >= 1 else f"{x:,.4f}"


def clean(df):
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df.dropna(subset=["Close"])


class Market:
    """Real yfinance data, fetched at most once per ticker per run. Missing data is None, never made up."""

    def __init__(self):
        self._daily, self._intra = {}, {}

    def _get(self, cache, t, period, interval):
        if t not in cache:
            try:
                df = yf.download(t, period=period, interval=interval, progress=False)
                cache[t] = clean(df) if df is not None and len(df) else None
            except Exception as e:
                print("Price fetch failed:", t, interval, e)
                cache[t] = None
        return cache[t]

    def daily(self, t):
        return self._get(self._daily, t, "1y", "1d")

    def intraday(self, t):
        return self._get(self._intra, t, "5d", "5m")

    def price(self, t):
        for df in (self.intraday(t), self.daily(t)):
            if df is not None and len(df):
                return float(df["Close"].iloc[-1])
        return None

    def fresh(self, t, now):
        df = self.intraday(t)
        return df is not None and len(df) > 0 and pd.Timestamp(now) - df.index[-1] <= FRESH


# ---------- Accounts and shared safety rules ----------
def new_account():
    return {"cash": START_CASH, "positions": [], "trades": [], "keys": [], "keys_day": "", "benched": False, "diary": {}}


def new_race(key, now, season=1, champion=None):
    names = BOTS + [BENCH]
    return {"race": key, "season": season, "start": now.isoformat(), "champion": champion,
            "accounts": {n: new_account() for n in names},
            "history": [{"t": now.isoformat(), "v": {n: START_CASH for n in names}}]}


def value(a):
    return a["cash"] + sum(x["shares"] * x["mark"] for x in a["positions"])


def fee(rc, amount):
    return amount * CRYPTO_FEE if rc["crypto"] else STOCK_FEE


def season_end(doc):
    return datetime.fromisoformat(doc["start"]) + timedelta(days=SEASON_DAYS)


def days_left(doc, now):
    return max(0, math.ceil((season_end(doc) - now).total_seconds() / 86400))


def record(a, side, ticker, price, shares, f, reason, now, **extra):
    t = {"time": now.isoformat(), "side": side, "ticker": ticker, "price": price, "shares": shares,
         "fee": round(f, 2), "reason": reason, **extra}
    a["trades"].append(t)
    return t


def buy(rc, a, name, ticker, px, stop, reason, now, events, frac=MAX_POS, risk=None, target=None, trail=None, extra=None):
    """Open a position under the shared rules. Returns the trade, or None if a rule says no."""
    if a["benched"] or not px or px <= 0:
        return None
    today = now.astimezone(MEL).date().isoformat()
    if a.get("keys_day") != today:
        a["keys_day"], a["keys"] = today, []
    if ticker in a["keys"] or any(x["ticker"] == ticker for x in a["positions"]):
        return None  # duplicate guard: one buy per ticker per day, never while already holding it
    if stop is None or not 0 < stop < px:
        return None  # every position needs a stop loss below the price
    fill = px * (1 + SLIP)
    total = value(a)
    budget = min(frac, MAX_POS) * total
    if risk is not None:  # size so a stop-out loses about `risk` of the account, fees included
        per_unit = fill - stop * (1 - SLIP) + (2 * fill * CRYPTO_FEE if rc["crypto"] else 0)
        cash_risk = risk * total - (0 if rc["crypto"] else 2 * STOCK_FEE)
        if cash_risk <= 0:
            return None
        budget = min(budget, cash_risk / per_unit * fill)
    budget = min(budget, a["cash"] / (1 + CRYPTO_FEE) if rc["crypto"] else a["cash"] - STOCK_FEE)
    units = budget / fill
    units = math.floor(units * 1e6) / 1e6 if rc["crypto"] else math.floor(units)
    if units <= 0:
        return None
    cost = units * fill
    f = fee(rc, cost)
    a["cash"] -= cost + f
    a["positions"].append({"ticker": ticker, "shares": units, "entry": fill, "entry_px": px, "stop": stop,
                           "target": target, "trail": trail, "high": px, "mark": px, "fees": f,
                           "opened": now.isoformat(), "checked": now.isoformat(), "reason": reason, **(extra or {})})
    a["keys"].append(ticker)
    t = record(a, "BUY", ticker, fill, units, f, reason, now)
    events.append((name, t))
    return t


def sell(rc, a, name, pos, px, reason, now, events):
    """Close a position (allowed even when benched). P/L is after both fees and slippage."""
    fill = px * (1 - SLIP)
    proceeds = pos["shares"] * fill
    f = fee(rc, proceeds)
    pnl = proceeds - f - pos["shares"] * pos["entry"] - pos["fees"]
    a["cash"] += proceeds - f
    a["positions"].remove(pos)
    t = record(a, "SELL", pos["ticker"], fill, pos["shares"], f, reason, now, pnl=round(pnl, 2))
    events.append((name, t))
    return t


def stop_reason(pos, px):
    return f"Stop loss (the safety exit that caps the loss) hit at ${p(px)}."


def target_reason(pos, px):
    return f"Profit target (the planned exit price) reached at ${p(px)}."


def protect(rc, a, name, pos, mkt, now, events):
    """Walk the 5-minute bars since the last check, oldest first: stop, then target, then raise a trailing stop."""
    df = mkt.intraday(pos["ticker"])
    if df is None or not len(df):
        return None
    rows = df[df.index > pd.Timestamp(pos["checked"])]
    strat = STRATEGIES.get(name)
    for i, (ts, r) in enumerate(rows.iterrows()):
        if float(r["Low"]) <= pos["stop"]:
            px = min(pos["stop"], float(r["Open"]))
            return sell(rc, a, name, pos, px, (strat.stop_reason if strat else stop_reason)(pos, px), now, events)
        if pos.get("target") and float(r["High"]) >= pos["target"]:
            px = max(pos["target"], float(r["Open"]))
            return sell(rc, a, name, pos, px, (strat.target_reason if strat else target_reason)(pos, px), now, events)
        pos["high"] = max(pos["high"], float(r["High"]))
        if pos.get("trail"):
            pos["stop"] = max(pos["stop"], pos["high"] * (1 - pos["trail"]))
        if i < len(rows) - 1:
            pos["checked"] = ts.isoformat()  # the newest bar is still forming, so look at it again next run
    return None


def bench_buy(rc, a, mkt, now, events):
    """Buy and Hold: everything into the benchmark on day one, then never trades."""
    if a.get("bought"):
        return
    px = mkt.price(rc["bench"])
    if not px:
        return
    fill = px * (1 + SLIP)
    budget = a["cash"] / (1 + CRYPTO_FEE) if rc["crypto"] else a["cash"] - STOCK_FEE
    units = math.floor(budget / fill * 1e6) / 1e6 if rc["crypto"] else math.floor(budget / fill)
    if units <= 0:
        return
    f = fee(rc, units * fill)
    a["cash"] -= units * fill + f
    a["positions"].append({"ticker": rc["bench"], "shares": units, "entry": fill, "entry_px": px, "stop": None,
                           "target": None, "trail": None, "high": px, "mark": px, "fees": f,
                           "opened": now.isoformat(), "checked": now.isoformat(), "reason": "benchmark"})
    a["bought"] = True
    events.append((BENCH, record(a, "BUY", rc["bench"], fill, units, f,
                                 f"Benchmark (the yardstick to beat): all $50,000 into {rc['bench']} on day one, then never trades.", now)))


def tick(rc, doc, mkt, now, asx_open, events):
    """One trading pass. The stocks race only trades while the ASX is open and prices are fresh."""
    if not rc["crypto"] and not (asx_open and mkt.fresh(rc["bench"], now)):
        return False
    accts = doc["accounts"]
    for name, a in accts.items():
        for pos in list(a["positions"]):
            px = mkt.price(pos["ticker"])
            if px is not None:
                pos["mark"] = px
            if pos.get("stop") is not None:
                protect(rc, a, name, pos, mkt, now, events)
    bench_buy(rc, accts[BENCH], mkt, now, events)
    for name in BOTS:
        a = accts[name]
        strat = STRATEGIES.get(name)
        if strat:
            try:
                strat.trade(rc, a, name, mkt, now, events)
            except Exception as e:
                print("Bot failed:", rc["key"], name, e)
        if not a["benched"] and value(a) <= START_CASH * (1 - LOSS_BRAKE):
            a["benched"] = True
            events.append((name, record(a, "BENCHED", "", 0.0, 0, 0.0, f"Down {LOSS_BRAKE * 100:.0f}% this season, so the loss "
                                        "brake (an automatic stop on trading) benches me until the reset.", now)))
    h = doc["history"]
    if not h or now - datetime.fromisoformat(h[-1]["t"]) >= HISTORY_EVERY:
        h.append({"t": now.isoformat(), "v": {n: round(value(a), 2) for n, a in accts.items()}})
    return True


def standings(doc):
    return sorted(((n, value(a)) for n, a in doc["accounts"].items()), key=lambda x: -x[1])


def standings_text(doc):
    return "\n".join(f"{i}. {n} ${v:,.0f} ({(v / START_CASH - 1) * 100:+.1f}%)" for i, (n, v) in enumerate(standings(doc), 1))


def finish_season(rc, doc, now, notify):
    """Save the final results to the Hall of Fame, crown the best bot, announce it, and reset every account."""
    table = standings(doc)
    winner = next(n for n, _ in table if n in BOTS)
    hof = get("system", "hall_of_fame", None) or []
    if not any(e["race"] == rc["key"] and e["season"] == doc["season"] for e in hof):
        hof.append({"race": rc["key"], "season": doc["season"], "start": doc["start"], "end": now.isoformat(), "winner": winner,
                    "standings": [{"name": n, "value": round(v, 2), "pct": round((v / START_CASH - 1) * 100, 2)} for n, v in table]})
        put("system", "hall_of_fame", hof)
        notify(f"{rc['name']} season {doc['season']} final standings",
               f"Champion: {winner}.\n{standings_text(doc)}\nEvery account resets to $50,000 for season {doc['season'] + 1}.", "trophy", "high")
    return new_race(rc["key"], now, season=doc["season"] + 1, champion=winner)


def trade_line(name, t):
    if t["side"] == "BENCHED":
        return f"{name} is benched: {t['reason'][:1].lower()}{t['reason'][1:]}"
    return f"{name} {'bought' if t['side'] == 'BUY' else 'sold'} {t['ticker']} at ${p(t['price'])}: {t['reason']}"


def daily_summary(notify, now):
    """One push after 5pm Melbourne with each race's standings and every bot's trades that day."""
    mel = now.astimezone(MEL)
    if mel.hour < SUMMARY_HOUR:
        return
    state = get("system", "race_summary_state", None) or {}
    if state.get("day") == mel.date().isoformat():
        return
    parts = []
    for rc in RACES.values():
        doc = get("system", rc["doc"], None)
        if not doc:
            continue
        parts.append(f"{rc['name']} (season {doc['season']}, {days_left(doc, now)} days left)\n{standings_text(doc)}")
        for n, a in doc["accounts"].items():
            today = [t for t in a["trades"] if datetime.fromisoformat(t["time"]).astimezone(MEL).date() == mel.date()]
            if today:
                parts.append("\n".join(trade_line(n, t) for t in today))
    put("system", "race_summary_state", {"day": mel.date().isoformat()})  # saved first, so a retry never double-sends
    notify("Bot race: daily summary", "\n\n".join(parts) or "No race data yet.", "bar_chart")


def run(notify, asx_open, now=None):
    """One race pass for both races. Never raises: a failure in one race leaves the other running."""
    now = now or datetime.now(timezone.utc)
    try:
        mode = (get("system", "race_settings", None) or {}).get("pings", "trade")
    except Exception as e:
        print("Race settings load failed:", e)
        mode = "trade"
    import bots  # noqa: F401  registers the five bot strategies
    mkt = Market()
    for rc in RACES.values():
        try:
            doc = get("system", rc["doc"], None)
        except Exception as e:
            print("Race load failed:", rc["key"], e)
            continue  # never replace a saved race with a fresh one
        doc = doc or new_race(rc["key"], now)
        events = []
        try:
            tick(rc, doc, mkt, now, asx_open, events)
        except Exception as e:
            print("Race tick failed:", rc["key"], e)
        try:
            if now >= season_end(doc):
                doc = finish_season(rc, doc, now, notify)
        except Exception as e:
            print("Season end failed:", rc["key"], e)
        try:
            put("system", rc["doc"], doc)
        except Exception as e:
            print("Race save failed:", rc["key"], e)
            continue  # trades that were not saved are not announced
        for name, t in events:
            print(now.astimezone(MEL).strftime("%H:%M"), rc["name"], trade_line(name, t))
            if mode == "trade":
                notify(f"{rc['name']}: {name}", trade_line(name, t), "racing_car")
    if mode == "summary":
        try:
            daily_summary(notify, now)
        except Exception as e:
            print("Daily summary failed:", e)

"""Iron Paw race: five bots, Coach's Picks and a Buy and Hold benchmark, in a STOCKS race and a CRYPTO race.

Pretend money only. No real orders, ever. Prices come only from yfinance; a ticker with no data is skipped,
never filled in. Money keeps running (weekly $400 deposits, no resets); racers are ranked by time-weighted
return. Everything is stored in Supabase under owner "system".
"""
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from store import get, put

MEL = ZoneInfo("Australia/Melbourne")
VERSION = 2
DEPOSIT = 400.0                    # every racer, every Monday 9am Melbourne
SCORECARD_DAYS = 21                # Hall of Fame scorecard every 3 weeks
SLIP = 0.001                       # 0.1% against us on every fill
COINSPOT_FEE = 0.01                # CoinSpot instant buy/sell: 1% of the trade
MAX_STOCK_TRADE = 10000.0          # CommSec tiers we were given stop at $10,000
MAX_FEE_PCT = 0.02                 # never trade if fees are more than 2% of the trade
MAX_POS = 0.25                     # max 25% of a racer's account in one position
LOSS_BRAKE = 0.15                  # 15% below its peak: stops buying until it recovers or the next scorecard
HISTORY_EVERY = timedelta(minutes=30)
FRESH = timedelta(minutes=30)      # stocks race only trades on bars this recent (skips holidays)
SUMMARY_HOUR = 17                  # daily summary push, Melbourne time

STOCKS = ["ALL.AX", "ANZ.AX", "BHP.AX", "BOE.AX", "CBA.AX", "COL.AX", "CSL.AX", "EVN.AX", "FMG.AX", "GMG.AX",
          "IGO.AX", "LYC.AX", "MIN.AX", "MQG.AX", "NAB.AX", "NST.AX", "PDN.AX", "PLS.AX", "QBE.AX", "REA.AX",
          "RIO.AX", "STO.AX", "TCL.AX", "TLS.AX", "WBC.AX", "WDS.AX", "WES.AX", "WOW.AX", "WTC.AX", "XRO.AX"]
CRYPTO = ["BTC-AUD", "ETH-AUD", "SOL-AUD", "XRP-AUD", "BNB-AUD", "ADA-AUD", "DOGE-AUD", "AVAX-AUD",
          "LINK-AUD", "DOT-AUD", "LTC-AUD", "BCH-AUD"]   # AUD pairs, so prices and fees are in Australian dollars
BOTS = ["Tyler", "Ryan", "Nathan", "Newton", "Morpheus"]
COACH = "Coach's Picks"
BENCH = "Buy and Hold"
RACERS = BOTS + [COACH, BENCH]
ALL_RACES = {"stocks": {"key": "stocks", "name": "STOCKS", "doc": "race_stocks", "tickers": STOCKS, "bench": "VAS.AX", "crypto": False,
                        "start_cash": 400.0, "broker": "CommSec"},
             "crypto": {"key": "crypto", "name": "CRYPTO", "doc": "race_crypto", "tickers": CRYPTO, "bench": "BTC-AUD", "crypto": True,
                        "start_cash": 5000.0, "broker": "CoinSpot"}}
ENABLED = ["stocks", "crypto"]     # both races on: STOCKS while the ASX is open, CRYPTO 24/7
RACES = {k: ALL_RACES[k] for k in ENABLED}
STRATEGIES = {}                    # bot name -> strategy object with .trade(); filled in by bots.py
RISK = {"check": None}             # optional pre-trade check: f(rc, a, name, trade) -> (approved, reason)


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
def new_account(cash):
    return {"cash": cash, "positions": [], "trades": [], "keys": [], "keys_day": "", "benched": False, "diary": {},
            "contributed": cash, "fees_paid": 0.0, "index": 1.0, "base": cash, "peak": 1.0, "sc_index": 1.0}


def next_monday_9(after):
    """The next Monday 9:00am Melbourne strictly after `after` (daylight saving handled)."""
    m = after.astimezone(MEL)
    d = m.date() + timedelta(days=(7 - m.weekday()) % 7)
    t = datetime(d.year, d.month, d.day, 9, 0, tzinfo=MEL)
    if t <= m:
        d += timedelta(days=7)
        t = datetime(d.year, d.month, d.day, 9, 0, tzinfo=MEL)
    return t.astimezone(timezone.utc)


def new_race(rc, now):
    return {"race": rc["key"], "version": VERSION, "start": now.isoformat(), "scorecard": 1, "sc_start": now.isoformat(),
            "champion": None, "next_deposit": next_monday_9(now).isoformat(), "coach_orders": [],
            "accounts": {n: new_account(rc["start_cash"]) for n in RACERS},
            "history": [{"t": now.isoformat(), "v": {n: rc["start_cash"] for n in RACERS}, "r": {n: 0.0 for n in RACERS}}]}


def value(a):
    return a["cash"] + sum(x["shares"] * x["mark"] for x in a["positions"])


def twr(a):
    """Time-weighted % return: growth of the money, ignoring when deposits arrived."""
    return (a["index"] - 1) * 100


def update_index(a):
    v = value(a)
    if a["base"] > 0:
        a["index"] *= v / a["base"]
    a["base"] = v
    a["peak"] = max(a["peak"], a["index"])


def fee(rc, amount):
    """CoinSpot: 1% of the trade. CommSec: $5 to $1,000, $10 to $3,000, $19.95 to $10,000 (None above that)."""
    if rc["crypto"]:
        return amount * COINSPOT_FEE
    if amount <= 1000:
        return 5.0
    if amount <= 3000:
        return 10.0
    if amount <= MAX_STOCK_TRADE:
        return 19.95
    return None


def scorecard_end(doc):
    return datetime.fromisoformat(doc["sc_start"]) + timedelta(days=SCORECARD_DAYS)


def days_left(doc, now):
    return max(0, math.ceil((scorecard_end(doc) - now).total_seconds() / 86400))


def record(a, side, ticker, price, shares, f, reason, now, **extra):
    t = {"time": now.isoformat(), "side": side, "ticker": ticker, "price": price, "shares": shares,
         "fee": round(f, 2), "reason": reason, **extra}
    a["trades"].append(t)
    return t


def reject(a, why):
    a["last_reject"] = why
    return None


def buy(rc, a, name, ticker, px, stop, reason, now, events, frac=MAX_POS, risk=None, target=None, trail=None, extra=None, dollars=None):
    """Open a position under the shared rules. Returns the trade, or None (the reason is kept in a["last_reject"])."""
    if a["benched"]:
        return reject(a, "loss brake is on")
    if not px or px <= 0:
        return reject(a, "no price")
    today = now.astimezone(MEL).date().isoformat()
    if a.get("keys_day") != today:
        a["keys_day"], a["keys"] = today, []
    if ticker in a["keys"] or any(x["ticker"] == ticker for x in a["positions"]):
        return reject(a, "already bought this signal")  # duplicate guard
    if stop is None or not 0 < stop < px:
        return reject(a, "no valid stop loss")  # every position needs a stop below the price
    fill = px * (1 + SLIP)
    total = value(a)
    budget = min(frac, MAX_POS) * total
    if dollars is not None:
        budget = min(budget, dollars)
    if not rc["crypto"]:
        budget = min(budget, MAX_STOCK_TRADE)
    if risk is not None:  # size so a stop-out loses about `risk` of the account, fees included
        per_unit = fill - stop * (1 - SLIP) + (2 * fill * COINSPOT_FEE if rc["crypto"] else 0)
        cash_risk = risk * total - (0 if rc["crypto"] else 2 * fee(rc, max(budget, 1)))
        if cash_risk <= 0:
            return reject(a, "account too small for risk-based sizing")
        budget = min(budget, cash_risk / per_unit * fill)
    budget = min(budget, a["cash"] / (1 + COINSPOT_FEE) if rc["crypto"] else a["cash"] - fee(rc, min(a["cash"], MAX_STOCK_TRADE)))
    units = budget / fill
    units = math.floor(units * 1e6) / 1e6 if rc["crypto"] else math.floor(units)
    if units <= 0:
        return reject(a, "not enough cash")
    cost = units * fill
    f = fee(rc, cost)
    if f is None or cost + f > a["cash"] + 1e-9:
        return reject(a, "not enough cash")
    if f > MAX_FEE_PCT * cost:
        return reject(a, f"fees ${f:,.2f} would be {f / cost * 100:.1f}% of a ${cost:,.2f} trade (limit 2%)")
    if RISK["check"]:
        ok, why = RISK["check"](rc, a, name, {"ticker": ticker, "price": fill, "units": units, "cost": round(cost, 2), "fee": round(f, 2),
                                              "stop": stop, "target": target, "reason": reason})
        if not ok:
            events.append((name, {"time": now.isoformat(), "side": "BLOCKED", "ticker": ticker, "price": fill, "shares": units,
                                  "fee": 0.0, "reason": why}))
            return reject(a, f"risk manager blocked it: {why}")
    a["cash"] -= cost + f
    a["fees_paid"] += f
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
    if f is None:  # above the CommSec tiers: never invent a fee, use the top tier we were given
        f = fee(rc, MAX_STOCK_TRADE)
    pnl = proceeds - f - pos["shares"] * pos["entry"] - pos["fees"]
    a["cash"] += proceeds - f
    a["fees_paid"] += f
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
    """Buy and Hold: puts each deposit into the benchmark as it arrives, never sells."""
    px = mkt.price(rc["bench"])
    if not px:
        return
    fill = px * (1 + SLIP)
    budget = a["cash"] / (1 + COINSPOT_FEE) if rc["crypto"] else a["cash"] - fee(rc, min(a["cash"], MAX_STOCK_TRADE))
    budget = budget if rc["crypto"] else min(budget, MAX_STOCK_TRADE)
    units = math.floor(budget / fill * 1e6) / 1e6 if rc["crypto"] else math.floor(budget / fill)
    if units <= 0:
        return
    f = fee(rc, units * fill)
    if f is None or f > MAX_FEE_PCT * units * fill or units * fill + f > a["cash"] + 1e-9:
        return  # waits for more cash rather than paying more than 2% in fees
    a["cash"] -= units * fill + f
    a["fees_paid"] += f
    held = next((x for x in a["positions"] if x["ticker"] == rc["bench"]), None)
    if held:  # top up the one holding at an average entry price
        n = held["shares"] + units
        held["entry"] = (held["entry"] * held["shares"] + fill * units) / n
        held["shares"], held["fees"], held["mark"] = n, held["fees"] + f, px
    else:
        a["positions"].append({"ticker": rc["bench"], "shares": units, "entry": fill, "entry_px": px, "stop": None,
                               "target": None, "trail": None, "high": px, "mark": px, "fees": f,
                               "opened": now.isoformat(), "checked": now.isoformat(), "reason": "benchmark"})
    events.append((BENCH, record(a, "BUY", rc["bench"], fill, units, f,
                                 f"Benchmark (the yardstick to beat): puts each deposit into {rc['bench']} as it arrives and never sells.", now)))


def deposit(rc, doc, now):
    """Every Monday 9am Melbourne, every racer gets another $400."""
    while now >= datetime.fromisoformat(doc["next_deposit"]):
        for a in doc["accounts"].values():
            update_index(a)
            a["cash"] += DEPOSIT
            a["contributed"] += DEPOSIT
            a["base"] = value(a)
        doc["next_deposit"] = next_monday_9(datetime.fromisoformat(doc["next_deposit"])).isoformat()


def coach_orders(rc, doc, mkt, now, events):
    """Carry out Coach's Picks orders (written weekly by coach.py) once its market is open."""
    a = doc["accounts"][COACH]
    for o in [o for o in doc.get("coach_orders", []) if o.get("status") == "pending"]:
        t = buy(rc, a, COACH, o["ticker"], mkt.price(o["ticker"]), o.get("stop"), o["reason"], now, events,
                frac=MAX_POS, target=o.get("target"), dollars=o["dollars"])
        o["status"], o["done"] = ("bought", now.isoformat()) if t else ("skipped", now.isoformat())
        if not t:
            o["why"] = a.get("last_reject", "")


def tick(rc, doc, mkt, now, asx_open, events):
    """One trading pass. The stocks race only trades while the ASX is open and prices are fresh."""
    if not rc["crypto"] and not (asx_open and mkt.fresh(rc["bench"], now)):
        return False
    doc["last_trading_day"] = now.astimezone(MEL).date().isoformat()
    accts = doc["accounts"]
    for name, a in accts.items():
        for pos in list(a["positions"]):
            px = mkt.price(pos["ticker"])
            if px is not None:
                pos["mark"] = px
            if pos.get("stop") is not None:
                protect(rc, a, name, pos, mkt, now, events)
    bench_buy(rc, accts[BENCH], mkt, now, events)
    coach_orders(rc, doc, mkt, now, events)
    for name in BOTS:
        strat = STRATEGIES.get(name)
        if strat:
            try:
                strat.trade(rc, accts[name], name, mkt, now, events)
            except Exception as e:
                print("Bot failed:", rc["key"], name, e)
    for name, a in accts.items():
        update_index(a)
        braked = name != BENCH and a["index"] <= a["peak"] * (1 - LOSS_BRAKE)
        if braked and not a["benched"]:
            events.append((name, record(a, "BENCHED", "", 0.0, 0, 0.0, f"Down {LOSS_BRAKE * 100:.0f}% from my peak, so the loss brake "
                                        "(an automatic stop on buying) is on until I recover or the next scorecard.", now)))
        a["benched"] = braked
    h = doc["history"]
    if not h or now - datetime.fromisoformat(h[-1]["t"]) >= HISTORY_EVERY:
        h.append({"t": now.isoformat(), "v": {n: round(value(a), 2) for n, a in accts.items()}, "r": {n: round(twr(a), 3) for n, a in accts.items()}})
    return True


def standings(doc):
    """Ranked by time-weighted % return on money put in."""
    return sorted(((n, value(a)) for n, a in doc["accounts"].items()), key=lambda x: -twr(doc["accounts"][x[0]]))


def standings_text(doc):
    A = doc["accounts"]
    return "\n".join(f"{i}. {n} {twr(A[n]):+.1f}% (${v:,.0f} from ${A[n]['contributed']:,.0f} in, fees ${A[n]['fees_paid']:,.2f}, "
                     f"{sum(1 for t in A[n]['trades'] if t['side'] in ('BUY', 'SELL'))} trades)" for i, (n, v) in enumerate(standings(doc), 1))


def finish_scorecard(rc, doc, now, notify):
    """Every 3 weeks: save each racer's % for the period to the Hall of Fame and crown a champion. No reset."""
    A = doc["accounts"]
    rows = sorted(((n, (a["index"] / a["sc_index"] - 1) * 100) for n, a in A.items()), key=lambda x: -x[1])
    winner = next(n for n, _ in rows if n != BENCH)
    end = scorecard_end(doc)
    hof = get("system", "hall_of_fame", None) or []
    if not any(e.get("race") == rc["key"] and e.get("scorecard") == doc["scorecard"] for e in hof):
        hof.append({"race": rc["key"], "scorecard": doc["scorecard"], "start": doc["sc_start"], "end": end.isoformat(), "winner": winner,
                    "results": [{"name": n, "pct": round(pct, 2), "value": round(value(A[n]), 2), "contributed": A[n]["contributed"],
                                 "fees": round(A[n]["fees_paid"], 2)} for n, pct in rows]})
        put("system", "hall_of_fame", hof)
        notify(f"{rc['name']} scorecard {doc['scorecard']} (3 weeks)",
               f"Champion: {winner}.\n" + "\n".join(f"{i}. {n} {pct:+.1f}%" for i, (n, pct) in enumerate(rows, 1)) + "\nThe money keeps running.",
               "trophy", "high")
    for a in A.values():
        a["sc_index"], a["peak"], a["benched"] = a["index"], a["index"], False
    doc.update(scorecard=doc["scorecard"] + 1, sc_start=end.isoformat(), champion=winner)
    return doc


def trade_line(name, t):
    if t["side"] == "BENCHED":
        return f"{name} is benched: {t['reason'][:1].lower()}{t['reason'][1:]}"
    if t["side"] == "BLOCKED":
        return f"Risk manager blocked {name} buying {t['ticker']} at ${p(t['price'])}: {t['reason']}"
    return f"{name} {'bought' if t['side'] == 'BUY' else 'sold'} {t['ticker']} at ${p(t['price'])}: {t['reason']}"


def daily_summary(notify, now):
    """One push after 5pm Melbourne with each race's standings and every bot's trades that day."""
    mel = now.astimezone(MEL)
    if mel.hour < SUMMARY_HOUR or mel.weekday() >= 5:  # no summary on Saturdays and Sundays
        return
    state = get("system", "race_summary_state", None) or {}
    if state.get("day") == mel.date().isoformat():
        return
    stocks = get("system", ALL_RACES["stocks"]["doc"], None) or {}
    if stocks.get("last_trading_day") != mel.date().isoformat():
        return  # the ASX did not trade today (public holiday), so no summary
    parts = []
    for rc in RACES.values():
        doc = get("system", rc["doc"], None)
        if not doc:
            continue
        parts.append(f"{rc['name']} (scorecard in {days_left(doc, now)} days)\n{standings_text(doc)}")
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
        mode = (get("system", "race_settings", None) or {}).get("pings", "summary")
    except Exception as e:
        print("Race settings load failed:", e)
        mode = "summary"
    import bots  # noqa: F401  registers the five bot strategies
    mkt = Market()
    for rc in RACES.values():
        try:
            doc = get("system", rc["doc"], None)
        except Exception as e:
            print("Race load failed:", rc["key"], e)
            continue  # never replace a saved race with a fresh one
        if doc and doc.get("version") != VERSION:  # old $50,000 race: keep a copy, then start the new money model
            try:
                put("system", rc["doc"] + "_v1", doc)
            except Exception as e:
                print("Race archive failed:", rc["key"], e)
                continue
            doc = None
        doc = doc or new_race(rc, now)
        events = []
        try:
            deposit(rc, doc, now)
            tick(rc, doc, mkt, now, asx_open, events)
        except Exception as e:
            print("Race tick failed:", rc["key"], e)
        try:
            while now >= scorecard_end(doc):
                doc = finish_scorecard(rc, doc, now, notify)
        except Exception as e:
            print("Scorecard failed:", rc["key"], e)
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

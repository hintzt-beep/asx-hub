"""Backtest: replays the Iron Paw trading system over past yfinance prices. Paper money only.

It runs the live code, not copies: race.deposit / race.tick / race.close_scorecard (fees, slippage, $400 weekly deposits,
starting cash, stop losses, 25% position cap, duplicate guard, loss brake), the five bots in bots.py, race.coach_orders,
coach.candidates / coach.check_pick, shadow.decide and the alerter's trend score. The market it hands them only ever
contains bars that had closed at that moment, so no decision can see the future.

  python backtest.py                    stocks: 3 years of daily bars; crypto: 2 years of hourly bars (daily before that)
  python backtest.py --stock-days 400 --crypto-days 60 --no-save    a quicker run
"""
import argparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

import ai
import coach
import race
import shadow
from alerter import LONG_LIST, SHADOW_FEE, best_long_idea, shadow_shares, trend_score
from store import get, put

SYD = ZoneInfo("Australia/Sydney")
MEL = race.MEL
PRACTICE = 0.70                    # first 70% of the timeline is "practice", the last 30% is "test"
CRYPTO_FEES = {"instant": 0.01, "markets": 0.001}   # CoinSpot Instant 1% (live) and CoinSpot Markets 0.1%
OVERFIT = "probably luck (overfit)"


# ---------- Past prices, stamped with the moment each bar closed (UTC) ----------
def fetch(t, **kw):
    try:
        df = yf.download(t, progress=False, **kw)
    except Exception as e:
        print("Price fetch failed:", t, e)
        return None
    if df is None or not len(df):
        return None
    return race.clean(df)


def stamp_days(df, tz, close_hour):
    """Daily bars: each bar closes at close_hour on its date in tz."""
    days = pd.to_datetime(pd.Index(df.index).date)
    df = df.copy()
    df.index = (days.tz_localize(tz) + pd.Timedelta(hours=close_hour)).tz_convert("UTC")
    return df


def stamp_hours(df):
    """Hourly bars: yfinance stamps the start of the hour; the bar closes an hour later."""
    df = df.copy()
    idx = pd.DatetimeIndex(df.index)
    df.index = (idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")) + pd.Timedelta(hours=1)
    return df


class HistMarket:
    """The live Market's interface over past data. Everything it returns closed at or before `now`."""

    def __init__(self, daily, intra, crypto):
        self.daily_all, self.intra_all, self.crypto = daily, intra, crypto
        self.now, self.views, self._cache = None, {}, {}

    def at(self, now):
        self.now, self.views, self._cache = now, {}, {}

    def _upto(self, df, n):
        i = df.index.searchsorted(self.now, side="right")
        return df.iloc[max(0, i - n):i]

    def daily(self, t):
        if ("d", t) in self._cache:
            return self._cache[("d", t)]
        df, out = self.daily_all.get(t), None
        if df is not None:
            out = self._upto(df, 252)  # the live system looks at one year of daily bars
            if self.crypto and self.intra_all.get(t) is not None:  # today so far, built from the hours that have closed
                h = self.intra_all[t]
                part = h[(h.index > self.now.replace(hour=0, minute=0, second=0, microsecond=0)) & (h.index <= self.now)]
                if len(part):
                    row = pd.DataFrame({"Open": [float(part["Open"].iloc[0])], "High": [float(part["High"].max())], "Low": [float(part["Low"].min())],
                                        "Close": [float(part["Close"].iloc[-1])], "Volume": [float(part["Volume"].sum())]}, index=[self.now])
                    out = pd.concat([out.iloc[-251:], row])
        out = out if out is not None and len(out) else None
        self._cache[("d", t)] = out
        return out

    def intraday(self, t):
        if ("i", t) not in self._cache:
            src = self.intra_all.get(t) if self.crypto else self.daily_all.get(t)
            out = self._upto(src, 120 if self.crypto else 30) if src is not None else None
            self._cache[("i", t)] = out if out is not None and len(out) else None
        return self._cache[("i", t)]

    def price(self, t):
        if ("p", t) not in self._cache:
            self._cache[("p", t)] = next((float(df["Close"].iloc[-1]) for df in (self.intraday(t), self.daily(t)) if df is not None and len(df)), None)
        return self._cache[("p", t)]

    def fresh(self, t, now):
        df = self.intraday(t)
        return df is not None and len(df) > 0 and df.index[-1] == now


# ---------- One race, replayed through the live engine ----------
def next_pick_time(after):
    """Coach's Picks run on Monday at 9:30am Melbourne."""
    t = race.next_monday_9(after - timedelta(minutes=30)).astimezone(MEL)
    return (t + timedelta(minutes=30)).astimezone(timezone.utc)


class Run:
    """One replay of a race: its own race doc, fee setting and risk-manager switch."""

    def __init__(self, rc, start, fee, risk):
        self.rc, self.fee, self.risk = rc, fee, risk
        self.doc, self.blocks, self.picks_log, self.next_pick = race.new_race(rc, start), [], [], next_pick_time(start)

    def review(self, now):
        def check(payload):
            ok, why = ai.risk_rules(payload)
            if not ok:
                self.blocks.append({"bot": payload["bot"], "ticker": payload["trade"]["ticker"], "reason": why, "time": now.isoformat()})
            return ok, why
        return lambda rc, a, n, t: race.risk_gate(self.doc, rc, a, n, t, now, reviewer=check)

    def step(self, mkt, now):
        rc, doc = self.rc, self.doc
        race.COINSPOT_FEE = self.fee
        race.RISK["check"] = self.review(now) if self.risk else None
        race.deposit(rc, doc, now)
        while now >= self.next_pick:  # Coach's Picks, rule-based estimate
            picks = coach.rule_picks(rc, coach.candidates(rc, mkt), doc["accounts"][race.COACH])
            doc["coach_orders"].extend({"ticker": o["ticker"], "dollars": o["dollars"], "stop": o["stop"], "reason": f"Coach's pick: {o['reason']}",
                                        "status": "pending", "created": now.isoformat()} for o in picks)
            self.picks_log.append({"time": now.isoformat(), "picks": len(picks)})
            self.next_pick = next_pick_time(self.next_pick + timedelta(minutes=1))
        race.tick(rc, doc, mkt, now, True, [])
        while now >= race.scorecard_end(doc):
            race.close_scorecard(doc)  # resets each loss brake's peak, as live


def simulate(rc, mkt, times, variants):
    """Replay every variant over the same bars, side by side, so each moment's indicators are worked out once."""
    runs = {k: Run(rc, times[0], fee, risk) for k, (fee, risk) in variants.items()}
    live_fee = race.COINSPOT_FEE
    try:
        for i, now in enumerate(times):
            mkt.at(now)
            for r in runs.values():
                r.step(mkt, now)
            if i % 1000 == 999:
                print(f"  {i + 1}/{len(times)}", flush=True)
    finally:
        race.COINSPOT_FEE, race.RISK["check"] = live_fee, None
    return runs


# ---------- Scoring ----------
def metrics(doc, name, t0, t1):
    hist = [(datetime.fromisoformat(h["t"]), h) for h in doc["history"]]
    seg = [h for t, h in hist if t0 <= t <= t1 and name in h.get("r", {})]
    if len(seg) < 2:
        return None
    index = [1 + h["r"][name] / 100 for h in seg]
    peak = dd = 0.0
    for x in index:
        peak = max(peak, x)
        dd = max(dd, (peak - x) / peak * 100)
    trades = [t for t in doc["accounts"][name]["trades"] if t["side"] in ("BUY", "SELL") and t0 < datetime.fromisoformat(t["time"]) <= t1]
    sells = [t for t in trades if t["side"] == "SELL"]
    wins = [t["pnl"] for t in sells if t.get("pnl", 0) > 0]
    losses = [t["pnl"] for t in sells if t.get("pnl", 0) <= 0]
    return {"final_value": round(seg[-1]["v"][name], 2), "return_pct": round((index[-1] / index[0] - 1) * 100, 2),
            "trades": len(trades), "win_rate_pct": round(len(wins) / len(sells) * 100, 1) if sells else None,
            "avg_win": round(sum(wins) / len(wins), 2) if wins else None, "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
            "max_drawdown_pct": round(dd, 2), "fees": round(sum(t["fee"] for t in trades), 2)}


def score_race(doc, times):
    t0, split, t1 = times[0], times[int(len(times) * PRACTICE)], times[-1]
    racers = {}
    for part, (a, b) in (("practice", (t0, split)), ("test", (split, t1))):
        bench = metrics(doc, race.BENCH, a, b)
        for n in race.RACERS:
            m = metrics(doc, n, a, b)
            if m and bench:
                m["vs_buy_and_hold_pct"] = round(m["return_pct"] - bench["return_pct"], 2)
            racers.setdefault(n, {})[part] = m
    for n, r in racers.items():
        p, t = r.get("practice"), r.get("test")
        if n != race.BENCH and p and t and ((p["vs_buy_and_hold_pct"] > 0 >= t["vs_buy_and_hold_pct"]) or (p["return_pct"] > 0 > t["return_pct"])):
            r["flag"] = OVERFIT
    pts = [(datetime.fromisoformat(h["t"]), h) for h in doc["history"]]
    test_pts = [(t, h) for t, h in pts if t >= split]
    step = max(1, len(test_pts) // 200)
    chart = {"t": [t.isoformat() for t, _ in test_pts[::step]], "series": {n: [h["v"].get(n) for _, h in test_pts[::step]] for n in race.RACERS}}
    return {"period": {"start": t0.isoformat(), "split": split.isoformat(), "end": t1.isoformat()}, "racers": racers, "chart": chart}


def risk_panel(scored_on, scored_off, blocks):
    movers = [n for n in race.RACERS if n != race.BENCH]
    trades = {(b["bot"], b["ticker"], b["time"][:10]) for b in blocks}  # bots retry a blocked buy; count it once a day
    out = {"blocked": len(trades), "attempts_blocked": len(blocks), "by_bot": {}, "examples": blocks[-5:], "limits": ai.RULE_LIMITS,
           "note": "Rule-based version of the risk manager's limits (risk per trade, fees, sector, daily loss). Sector limit applies to shares only."}
    for bot, _, _ in trades:
        out["by_bot"][bot] = out["by_bot"].get(bot, 0) + 1
    for part in ("practice", "test"):
        on = [scored_on["racers"][n][part]["return_pct"] for n in movers if scored_on["racers"][n].get(part)]
        off = [scored_off["racers"][n][part]["return_pct"] for n in movers if scored_off["racers"][n].get(part)]
        if on and off:
            diff = sum(on) / len(on) - sum(off) / len(off)
            out[part] = {"avg_return_with_pct": round(sum(on) / len(on), 2), "avg_return_without_pct": round(sum(off) / len(off), 2),
                         "difference_pct": round(diff, 2), "verdict": "helped" if diff > 0 else "hurt" if diff < 0 else "made no difference"}
    return out


def coach_panel(scored, picks_log):
    weeks = len(picks_log)
    return {"label": "rule-based estimate", "weeks": weeks, "weeks_with_picks": sum(1 for p in picks_log if p["picks"]),
            "picks": sum(p["picks"] for p in picks_log), "practice": scored["racers"][race.COACH].get("practice"),
            "test": scored["racers"][race.COACH].get("test")}


def run_races(rc, mkt, times, fees):
    """Each fee setting with the risk manager on, plus off for comparison. Returns {fee name: results}."""
    variants = {}
    for name, f in fees.items():
        variants[(name, True)], variants[(name, False)] = (f, True), (f, False)
    runs, out = simulate(rc, mkt, times, variants), {}
    for name in fees:
        on, off = runs[(name, True)], runs[(name, False)]
        scored = score_race(on.doc, times)
        scored["fee_pct"] = round(fees[name] * 100, 3) if rc["crypto"] else None
        scored["risk_manager"] = risk_panel(scored, score_race(off.doc, times), on.blocks)
        scored["coach"] = coach_panel(scored, on.picks_log)
        out[name] = scored
    return out


# ---------- Data for each race ----------
def stock_market(days):
    daily = {}
    for t in race.STOCKS + [race.ALL_RACES["stocks"]["bench"]]:
        df = fetch(t, period=f"{days + 400}d", interval="1d")
        if df is not None:
            daily[t] = stamp_days(df, SYD, 16)  # the ASX closes at 4pm Sydney time
    bench = daily.get(race.ALL_RACES["stocks"]["bench"])
    if bench is None:
        return None, []
    start = bench.index[-1] - pd.Timedelta(days=days)
    return HistMarket(daily, {}, crypto=False), [t.to_pydatetime() for t in bench.index if t >= start]


def crypto_market(days):
    daily, intra = {}, {}
    for t in race.CRYPTO:
        d = fetch(t, period="5y", interval="1d")
        h = fetch(t, period=f"{min(days, 729)}d", interval="1h")  # yfinance keeps about 2 years of hourly bars
        if d is not None:
            daily[t] = stamp_days(d, "UTC", 24)  # a UTC day's bar closes at midnight
        if h is not None:
            intra[t] = stamp_hours(h)
    bench = intra.get(race.ALL_RACES["crypto"]["bench"])
    if bench is None:
        return None, []
    return HistMarket(daily, intra, crypto=True), [t.to_pydatetime() for t in bench.index]


# ---------- Shadow bot on Ty's real holdings ----------
def shadow_replay():
    try:
        holdings = get("Ty", "holdings", []) or []  # read only, never written
    except Exception as e:
        return {"error": f"Couldn't read the holdings ({type(e).__name__})."}
    rows, skipped, longs = [], [], {}

    def closes(t, start):
        if (t, start) not in longs:
            df = fetch(t, start=start.strftime("%Y-%m-%d"), interval="1d")
            longs[(t, start)] = df["Close"] if df is not None else None
        return longs[(t, start)]

    for h in holdings:
        tk, qty, paid, bought = h.get("ticker"), float(h.get("qty") or 0), float(h.get("paid") or 0), h.get("bought")
        if not (tk and qty > 0 and paid > 0 and bought):
            skipped.append(tk or "?")
            continue
        day0 = datetime.strptime(str(bought)[:10], "%Y-%m-%d")
        start = day0 - timedelta(days=450)
        c = closes(tk, start)
        if c is None or not len(c):
            skipped.append(tk)
            continue
        days = [d for d in c.index if d.to_pydatetime().replace(tzinfo=None) >= day0]
        sold = None
        for d in days:
            score, px = trend_score(c[c.index <= d])
            if score is None:
                continue
            dec = shadow.decide(qty, paid, px, score, bought, today=d.date())
            if dec["word"] == "SELL":
                sold = {"date": str(d.date()), "price": round(px, 4), "proceeds": round(qty * px - SHADOW_FEE, 2), "reason": dec["reason"]}
                break
        hold_value = qty * float(c.iloc[-1])
        row = {"ticker": tk, "qty": qty, "paid": paid, "bought": str(bought)[:10], "hold_value": round(hold_value, 2), "sold": sold, "bought_instead": None}
        shadow_value = hold_value
        if sold:
            shadow_value = sold["proceeds"]  # cash until a Long term idea scores BUY
            for d in [d for d in days if str(d.date()) >= sold["date"]]:
                idea = best_long_idea(tk, score_of=lambda t, d=d: trend_score(_upto_day(closes(t, start), d)))
                if not idea:
                    continue
                lc = closes(idea[0], start)
                px = float(_upto_day(lc, d).iloc[-1])
                shares, fill = shadow_shares(sold["proceeds"], px)
                if shares >= 1:
                    left = sold["proceeds"] - shares * fill - SHADOW_FEE
                    shadow_value = shares * float(lc.iloc[-1]) + left
                    row["bought_instead"] = {"ticker": idea[0], "date": str(d.date()), "shares": shares, "price": round(fill, 4), "score": idea[1]}
                break
        row["shadow_value"] = round(shadow_value, 2)
        row["difference"] = round(shadow_value - hold_value, 2)
        rows.append(row)
    return {"holdings": rows, "skipped": skipped, "shadow_total": round(sum(r["shadow_value"] for r in rows), 2),
            "hold_total": round(sum(r["hold_value"] for r in rows), 2)}


def _upto_day(series, d):
    if series is None:
        return None
    return series[series.index <= d]


# ---------- Plain-English summary ----------
def summary(results):
    lines = []
    names = {"stocks": "STOCKS", "crypto_instant": "CRYPTO (CoinSpot Instant, 1% fee)", "crypto_markets": "CRYPTO (CoinSpot Markets, 0.1% fee)"}
    for key, res in results["races"].items():
        R = res["racers"]
        bench = (R.get(race.BENCH) or {}).get("test")
        if not bench:
            continue
        lines.append(f"{names[key]}, test period (data the rules never saw): Buy and Hold returned {bench['return_pct']:+.1f}%.")
        beat = [f"{n} ({r['test']['vs_buy_and_hold_pct']:+.1f}% vs Buy and Hold)" for n, r in R.items()
                if n != race.BENCH and r.get("test") and r["test"]["vs_buy_and_hold_pct"] > 0]
        lag = [n for n, r in R.items() if n != race.BENCH and r.get("test") and r["test"]["vs_buy_and_hold_pct"] <= 0]
        lines.append(("Working: " + ", ".join(beat) + " beat Buy and Hold on unseen data.") if beat else "Working: no racer beat Buy and Hold on unseen data.")
        if lag:
            lines.append("Not working: " + ", ".join(lag) + " did no better than Buy and Hold on unseen data.")
        flagged = [n for n, r in R.items() if r.get("flag")]
        if flagged:
            lines.append(f"Probably luck (overfit): {', '.join(flagged)} won in practice but lost in the test period.")
        rm = res.get("risk_manager", {}).get("test")
        if rm:
            lines.append(f"Risk manager rules would have blocked {res['risk_manager']['blocked']} trades; in the test period blocking "
                         f"{rm['verdict']} (bots averaged {rm['avg_return_with_pct']:+.1f}% with it, {rm['avg_return_without_pct']:+.1f}% without).")
        cp = res.get("coach", {}).get("test")
        if cp:
            lines.append(f"Coach's Picks (rule-based estimate) returned {cp['return_pct']:+.1f}% in the test period.")
    inst, mkts = results["races"].get("crypto_instant"), results["races"].get("crypto_markets")
    if inst and mkts:
        avg = lambda res: sum(r["test"]["return_pct"] for n, r in res["racers"].items() if n not in (race.BENCH,) and r.get("test")) / max(1, len(race.RACERS) - 1)
        lines.append(f"Fees matter: in crypto the racers averaged {avg(mkts):+.1f}% on CoinSpot Markets (0.1%) against {avg(inst):+.1f}% on Instant (1%).")
    sh = results.get("shadow") or {}
    if sh.get("holdings"):
        diff = sh["shadow_total"] - sh["hold_total"]
        lines.append(f"Shadow bot on your real holdings: ${sh['shadow_total']:,.0f} against ${sh['hold_total']:,.0f} for just holding "
                     f"({'better' if diff > 0 else 'worse' if diff < 0 else 'the same'} by ${abs(diff):,.0f}).")
    lines.append("Past results don't promise future ones; trust the test period over practice.")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock-days", type=int, default=3 * 365)
    ap.add_argument("--crypto-days", type=int, default=730)
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()
    import bots  # noqa: F401  registers the five bot strategies
    results = {"run": datetime.now(timezone.utc).isoformat(), "races": {}, "notes": [
        "Same code as the live system; fees, slippage, $400 weekly deposits, stops, position caps, duplicate guard and loss brake included.",
        "Risk manager and Coach's Picks use rule-based stand-ins, since the AI may already know past prices.",
        "STOCKS: daily bars, so Tyler's breakout uses the recent 20-day high. CRYPTO: hourly bars."]}
    mkt, times = stock_market(args.stock_days)
    if times:
        print(f"STOCKS: {len(times)} days")
        results["races"]["stocks"] = run_races(race.ALL_RACES["stocks"], mkt, times, {"commsec": race.COINSPOT_FEE})["commsec"]
    mkt, times = crypto_market(args.crypto_days)
    if times:
        print(f"CRYPTO: {len(times)} hours, CoinSpot Instant 1% and Markets 0.1% fees")
        for name, res in run_races(race.ALL_RACES["crypto"], mkt, times, CRYPTO_FEES).items():
            results["races"][f"crypto_{name}"] = res
    results["shadow"] = shadow_replay()
    results["summary"] = summary(results)
    print("\n".join(results["summary"]))
    if not args.no_save:
        put("system", "backtest_results", results)
    return results


if __name__ == "__main__":
    main()

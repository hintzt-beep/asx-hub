"""The Coach for the Iron Paw race. Paper money only. No real orders, ever.

  python coach.py report             daily report: stats worked out in Python, one Claude call to write it up
  python coach.py picks [--scheduled] Coach's Picks for the week (0-3 per race), checked in Python, then queued
                                      for the race engine to buy in its own paper account

Never invents numbers: every figure in a report or pick comes from the race data or real yfinance prices.
"""
import sys
import uuid
from datetime import datetime, timezone

import ai
import race
from alerter import notify_ty
from bots import STYLES, Tyler, daily_view
from store import get, put

MEL = race.MEL
COACHED = race.BOTS + [race.COACH]

RULES = {"bots": STYLES, "fees": {"STOCKS": "CommSec: $5 per trade up to $1,000, $10 to $3,000, $19.95 to $10,000, plus 0.1% slippage",
                                  "CRYPTO": "CoinSpot Markets: 0.1% on every buy and sell, plus 0.1% slippage, prices in AUD"},
         "shared": "stop loss on every position, max 25% of an account in one position, no buy if fees are over 2% of the trade, "
                   "one buy per ticker per day, loss brake at 15% below the peak, $400 deposit every Monday, ranked by time-weighted return"}

REPORT_SYSTEM = (
    "You are the Coach for Iron Paw, a paper-trading race between bots (pretend money, no real orders). You get each racer's "
    "statistics, worked out in Python, for a STOCKS race (ASX shares, CommSec fees) and a CRYPTO race (AUD, CoinSpot fees), plus "
    "the bots' rules. Write a short report in plain English, using proper trading terms with a plain explanation in brackets, "
    "for example 'drawdown (the biggest fall from a high)'. Say what is working and what isn't, then suggest up to 3 small rule "
    "changes, each for one bot in one race, each with why. Only use numbers that appear in the data: never invent, estimate or "
    "round numbers into new ones. With fewer than 20 closed trades the evidence is thin, so say so. If there is too little data, "
    "say that and suggest nothing. You may also get the latest backtest (a replay of the same rules over past prices, split "
    "into a practice period and an unseen test period): use it as extra evidence, trust the test period over practice, and "
    "treat anything flagged 'probably luck (overfit)' with suspicion. You also get changes_already_made: rule changes already "
    "approved and live. Don't suggest those again; the backtest may predate them, so wait for a newer backtest before judging them.")
REPORT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "working", "not_working", "suggestions"],
    "properties": {
        "summary": {"type": "string"},
        "working": {"type": "array", "items": {"type": "string"}},
        "not_working": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["bot", "race", "change", "why", "confidence"],
            "properties": {"bot": {"type": "string", "enum": COACHED}, "race": {"type": "string", "enum": ["stocks", "crypto"]},
                           "change": {"type": "string"}, "why": {"type": "string"},
                           "confidence": {"type": "string", "enum": ["low", "medium", "high"]}}}}}}

PICKS_SYSTEM = (
    "You are the Coach for Iron Paw, a paper-trading race (pretend money, no real orders). Each Monday you may pick 0 to 3 trades "
    "for the Coach's Picks account in one race, using its available cash (it gets $400 a week and may save up). Picking nothing "
    "and saving the cash is fine when nothing looks good. Every pick needs a stop loss below the current price. Count the fees "
    "you are given: a trade whose fee is more than 2% of its size is not allowed, and one position may be at most 25% of the "
    "account. Use only the tickers and numbers given; never invent prices. Explain each pick in one or two plain-English "
    "sentences with trading terms explained in brackets, or explain why there is no pick.")


def picks_schema(tickers):
    return {"type": "object", "additionalProperties": False, "required": ["picks", "no_pick_reason"],
            "properties": {"no_pick_reason": {"type": "string"},
                           "picks": {"type": "array", "items": {
                               "type": "object", "additionalProperties": False, "required": ["ticker", "dollars", "stop", "reason"],
                               "properties": {"ticker": {"type": "string", "enum": tickers}, "dollars": {"type": "number"},
                                              "stop": {"type": "number"}, "reason": {"type": "string"}}}}}}


# ---------- Stats (Python only) ----------
def racer_stats(doc):
    A, hist = doc["accounts"], doc.get("history", [])
    bench = race.twr(A[race.BENCH])
    blocks = {}
    for e in doc.get("risk_log", []):
        if e["decision"] == "block":
            blocks[e["bot"]] = blocks.get(e["bot"], 0) + 1
    out = {}
    for n, a in A.items():
        sells = [t for t in a["trades"] if t["side"] == "SELL"]
        wins = [t["pnl"] for t in sells if t.get("pnl", 0) > 0]
        losses = [t["pnl"] for t in sells if t.get("pnl", 0) <= 0]
        index = [1 + h["r"][n] / 100 for h in hist if n in h.get("r", {})] + [a["index"]]
        peak = dd = 0.0
        for x in index:
            peak = max(peak, x)
            dd = max(dd, (peak - x) / peak * 100 if peak else 0)
        out[n] = {"closed_trades": len(sells), "buys": sum(1 for t in a["trades"] if t["side"] == "BUY"),
                  "win_rate_pct": round(len(wins) / len(sells) * 100, 1) if sells else None,
                  "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
                  "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
                  "fees_paid": round(a["fees_paid"], 2), "max_drawdown_pct": round(dd, 2),
                  "time_weighted_return_pct": round(race.twr(a), 2), "vs_buy_and_hold_pct": round(race.twr(a) - bench, 2),
                  "value": round(race.value(a), 2), "money_put_in": a["contributed"], "cash": round(a["cash"], 2),
                  "open_positions": len(a["positions"]), "loss_brake_on": a["benched"], "risk_manager_blocks": blocks.get(n, 0)}
    return out


# ---------- Daily report ----------
def backtest_brief():
    """The latest backtest, cut down to what the Coach needs: test and practice returns, vs Buy and Hold, flags, summary."""
    try:
        bt = get("system", "backtest_results", None)
    except Exception:
        bt = None
    if not bt:
        lab = lab_brief()
        return {"strategy_lab": lab} if lab else None
    brief = {"run": bt.get("run"), "summary": bt.get("summary", []), "races": {}}
    for key, res in bt.get("races", {}).items():
        brief["races"][key] = {n: {"test_return_pct": r["test"]["return_pct"], "practice_return_pct": (r.get("practice") or {}).get("return_pct"),
                                   "test_vs_buy_and_hold_pct": r["test"].get("vs_buy_and_hold_pct"), "test_trades": r["test"]["trades"],
                                   "flag": r.get("flag")} for n, r in res.get("racers", {}).items() if r.get("test")}
    lab = lab_brief()
    if lab:
        brief["strategy_lab"] = lab
    return brief


def lab_brief():
    """The Strategy Lab's verdicts and best survivors, cut down for the Coach (it explains them; it does not pick)."""
    try:
        lab = get("system", "lab_results", None)
    except Exception:
        lab = None
    if not lab:
        return None
    out = {"run": lab.get("run"), "summary": lab.get("summary", []), "markets": {}}
    for key, m in lab.get("markets", {}).items():
        for mode, r in (m.get("fees") or {}).items():
            out["markets"][f"{key}_{mode}"] = {"verdict": r.get("verdict"), "counts": r.get("counts"), "buy_and_hold": r.get("buy_and_hold"),
                                               "survivors": [{"plain": s["plain"], "test": s["test"], "practice_return_pct": s["practice"]["return_pct"]}
                                                             for s in r.get("survivors", [])[:3]]}
    return out


def changes_made():
    """Approved suggestions from earlier reports (bot, race, change, when), newest first, so the Coach doesn't repeat them."""
    try:
        reports = get("system", "coach_reports", None) or []
    except Exception:
        return []
    done = [{"bot": s["bot"], "race": s["race"], "change": s["change"], "approved_in_report": r.get("time", "")[:10]}
            for r in reports for s in r.get("suggestions", []) if s.get("status") == "approved"]
    return done[::-1][:12]


def run_report(now):
    stats = {}
    for key, rc in race.RACES.items():
        doc = race.load_race(rc, now, create=False)
        if doc:
            stats[key] = racer_stats(doc)
    if not stats:
        print("No race data yet, no report.")
        return None
    report = {"id": uuid.uuid4().hex[:8], "time": now.isoformat(), "stats": stats}
    try:
        data = ai.coach_json(REPORT_SYSTEM, {"races": stats, "rules": RULES, "backtest": backtest_brief(),
                                             "changes_already_made": changes_made()}, REPORT_SCHEMA)
    except Exception as e:
        report.update(summary=f"The Coach couldn't reach the AI today ({type(e).__name__}), so there is no written report. Today's stats are saved.",
                      working=[], not_working=[], suggestions=[], ai_error=str(e)[:300])
    else:
        sugg = []
        for s in data["suggestions"][:3]:
            n_trades = stats.get(s["race"], {}).get(s["bot"], {}).get("closed_trades", 0)  # the real count, not the model's
            sugg.append({**s, "id": uuid.uuid4().hex[:8], "trades": n_trades,
                         "confidence": "low" if n_trades < 20 else s["confidence"], "status": "new"})
        report.update(summary=data["summary"].strip(), working=data["working"], not_working=data["not_working"], suggestions=sugg)
    reports = get("system", "coach_reports", None) or []
    reports.append(report)
    put("system", "coach_reports", reports[-30:])
    lines = [report["summary"]] + [f"Idea for {s['bot']} ({s['race']}): {s['change']} ({s['trades']} trades, {s['confidence']} confidence)"
                                   for s in report["suggestions"]]
    notify_ty("Coach report", "\n".join(lines) + "\nDetails on the Suggestions tab.", "clipboard")
    print(report["summary"])
    return report


# ---------- Weekly Coach's Picks ----------
CRYPTO_SETUP = ("CRYPTO picks are limited to the one setup with Strategy Lab evidence: a coin whose last finished day closed above its "
                "55-day high on 1.5x+ normal volume, only while Bitcoin is above its 200-day average. Only coins with that setup are listed. "
                "A stop about 5% below the price matches the lab's rule.")


def crypto_setups(mkt, now):
    """(BTC above its 200-day?, set of coins with a 55-day-high breakout on 1.5x volume), on finished daily bars only."""
    btc = Tyler.closed_days(mkt, Tyler.LAB_FILTER, now)
    if btc is None or len(btc) < 200:
        return None, set()  # no Bitcoin data: no picks rather than a guess
    if float(btc["Close"].iloc[-1]) <= float(btc["Close"].tail(200).mean()):
        return False, set()
    hits = set()
    for t in race.CRYPTO:
        df = Tyler.closed_days(mkt, t, now)
        if df is None or len(df) < Tyler.LAB_HIGH + 21:
            continue
        level = float(df["High"].iloc[-Tyler.LAB_HIGH - 1:-1].max())
        avg_vol = float(df["Volume"].iloc[-21:-1].mean())
        if avg_vol > 0 and float(df["Close"].iloc[-1]) > level and float(df["Volume"].iloc[-1]) / avg_vol >= Tyler.LAB_VOL:
            hits.add(t)
    return True, hits


def candidates(rc, mkt):
    rows = {}
    allowed = None
    if rc["crypto"]:  # crypto: only the lab's breakout setup, and only while BTC is above its 200-day
        _, allowed = crypto_setups(mkt, getattr(mkt, "now", None) or datetime.now(timezone.utc))
    for t in rc["tickers"]:
        if allowed is not None and t not in allowed:
            continue
        v = daily_view(mkt, t)
        if v is None:
            continue
        c = v["close"]
        rows[t] = {"price": round(v["px"], 6), "rsi14": round(v["rsi"], 1), "sma20": round(v["sma20"], 6), "sma50": round(v["sma50"], 6),
                   "sma200": round(v["sma200"], 6) if v["sma200"] else None, "return_5d_pct": round((v["px"] / float(c.iloc[-6]) - 1) * 100, 2),
                   "return_20d_pct": round((v["px"] / float(c.iloc[-21]) - 1) * 100, 2), "volume_5d_vs_20d": round(v["vol5"] / v["vol20"], 2) if v["vol20"] else None,
                   "atr14": round(v["atr"], 6), "below_1y_high_pct": round((1 - v["px"] / float(c.max())) * 100, 2)}
    return rows


def check_pick(rc, p, cand, cash_left, acct_value):
    """Python checks for one pick. Returns (order, None) or (None, why_dropped)."""
    c = cand.get(p["ticker"])
    if not c:
        return None, "no real price data for this ticker"
    dollars, stop, px = float(p["dollars"]), float(p["stop"]), c["price"]
    f = race.fee(rc, dollars)
    if dollars <= 0 or f is None:
        return None, "trade size is outside the fee table"
    if dollars + f > cash_left + 1e-9:
        return None, f"needs ${dollars + f:,.2f} with fees but only ${cash_left:,.2f} cash is left"
    if dollars > race.MAX_POS * acct_value + 1e-9:
        return None, f"${dollars:,.2f} is more than 25% of the ${acct_value:,.2f} account"
    if f > race.MAX_FEE_PCT * dollars:
        return None, f"fee ${f:,.2f} is {f / dollars * 100:.1f}% of the trade (limit 2%)"
    if not 0 < stop < px:
        return None, f"stop ${stop} is not below the price ${px}"
    units = dollars / (px * (1 + race.SLIP))
    units = units if rc["crypto"] else int(units)
    if units <= 0:
        return None, "less than one share"
    return {"ticker": p["ticker"], "dollars": round(dollars, 2), "stop": stop, "price": px, "fee": round(f, 2), "units": units,
            "reason": p["reason"].strip()}, None


def rule_picks(rc, cand, a):
    """Rule-based estimate of Coach's Picks (used by backtests, since the AI may already know past prices):
    the best-scoring signals that week, 0 to 3 picks, each passing the same checks as the live Coach; cash saved otherwise."""
    def score(c):
        return (int(c["price"] > c["sma50"]) + int(bool(c["sma200"]) and c["sma50"] > c["sma200"]) + int(45 <= c["rsi14"] <= 65)
                + int(c["return_20d_pct"] > 0) + int((c["volume_5d_vs_20d"] or 0) > 1))
    ranked = sorted(((score(c), c["return_20d_pct"], t) for t, c in cand.items()), reverse=True)
    picks, cash_left, value = [], a["cash"], race.value(a)
    for sc, _, t in ranked:
        if sc < 4 or len(picks) == 3:
            break
        c = cand[t]
        dollars = min(cash_left / (3 - len(picks)) / (1 + (race.COINSPOT_FEE if rc["crypto"] else 0)), race.MAX_POS * value)
        if not rc["crypto"]:
            dollars -= race.fee(rc, dollars) or 0
        p = {"ticker": t, "dollars": round(dollars, 2), "stop": round(c["price"] - 2 * c["atr14"], 6),
             "reason": f"Rule-based estimate: score {sc}/5 (trend, RSI {c['rsi14']:.0f}, momentum and volume)."}
        order, _ = check_pick(rc, p, cand, cash_left, value)
        if order:
            picks.append(order)
            cash_left -= order["dollars"] + order["fee"]
    return picks


def pick_line(rc, o):
    name = o["ticker"].replace(".AX", "").replace("-AUD", "")
    if rc["crypto"]:
        return (f"CRYPTO (CoinSpot): BUY ${o['dollars']:,.2f} of {name} (about {o['units']:.6f} at ${o['price']:,.2f} AUD), "
                f"stop loss ${o['stop']:,.2f}, fee about ${o['fee']:,.2f}. Why: {o['reason']}")
    return (f"STOCKS (CommSec): BUY {name} about ${o['dollars']:,.2f} ({o['units']} shares at ${o['price']:,.2f}), "
            f"stop loss ${o['stop']:,.2f}, brokerage ${o['fee']:,.2f}. Why: {o['reason']}")


def run_picks(now, scheduled=False):
    mel = now.astimezone(MEL)
    if scheduled and not (mel.weekday() == 0 and mel.hour >= 9):
        print("Not Monday 9am Melbourne yet, no picks.")
        return None
    week = f"{mel.isocalendar().year}-W{mel.isocalendar().week:02d}"
    history = get("system", "coach_picks", None) or []
    if any(h["week"] == week for h in history):
        print("Picks already made for", week)
        return None
    mkt = race.Market()
    entry = {"week": week, "time": now.isoformat(), "races": {}}
    for key, rc in race.RACES.items():
        doc = race.load_race(rc, now, create=False)
        if not doc:
            continue
        race.deposit(rc, doc, now)  # make sure this Monday's $400 has landed
        a = doc["accounts"][race.COACH]
        cand = candidates(rc, mkt)
        res = {"cash": round(a["cash"], 2), "picks": [], "dropped": [], "no_pick_reason": ""}
        if rc["crypto"] and not cand:
            btc_up, _ = crypto_setups(mkt, now)
            res["no_pick_reason"] = ("No Bitcoin price data, so no crypto picks this week. Saving the cash." if btc_up is None else
                                     "Bitcoin is below its 200-day average, so no crypto picks (the lab's setup only works in an uptrend). Saving the cash."
                                     if not btc_up else "No coin closed at a 55-day high on strong volume this week, so no crypto picks. Saving the cash.")
        elif not cand:
            res["no_pick_reason"] = "No real price data was available, so no picks."
        else:
            payload = {"race": rc["name"], "fees": RULES["fees"][rc["name"]], "coach_account": {
                "cash": round(a["cash"], 2), "value": round(race.value(a), 2), "max_position": round(race.MAX_POS * race.value(a), 2),
                "open_positions": [{"ticker": x["ticker"], "value": round(x["shares"] * x["mark"], 2)} for x in a["positions"]]},
                "candidates": cand, **({"setup_rule": CRYPTO_SETUP} if rc["crypto"] else {})}
            try:
                data = ai.coach_json(PICKS_SYSTEM, payload, picks_schema(sorted(cand)))
            except Exception as e:
                res["no_pick_reason"] = f"The Coach couldn't reach the AI ({type(e).__name__}), so no picks this week; the cash is saved."
            else:
                cash_left, value = a["cash"], race.value(a)
                for p in data["picks"][:3]:
                    order, why = check_pick(rc, p, cand, cash_left, value)
                    if order:
                        res["picks"].append(order)
                        cash_left -= order["dollars"] + order["fee"]
                    else:
                        res["dropped"].append({**p, "why": why})
                if not res["picks"]:
                    res["no_pick_reason"] = data["no_pick_reason"].strip() or (
                        "The suggested picks didn't pass the checks (" + "; ".join(f"{d['ticker']}: {d['why']}" for d in res["dropped"]) + ").")
        if res["picks"]:
            doc.setdefault("coach_orders", []).extend(
                {"ticker": o["ticker"], "dollars": o["dollars"], "stop": o["stop"], "reason": f"Coach's pick: {o['reason']}",
                 "status": "pending", "week": week, "created": now.isoformat()} for o in res["picks"])
        put("system", rc["doc"], doc)
        entry["races"][key] = res
    if not entry["races"]:
        print("No race data yet, no picks.")
        return None
    history.append(entry)
    put("system", "coach_picks", history[-26:])
    lines = []
    for key, res in entry["races"].items():
        rc = race.RACES[key]
        lines += [pick_line(rc, o) for o in res["picks"]] or [f"{rc['name']}: no picks this week. {res['no_pick_reason']} Saving ${res['cash']:,.2f}."]
    notify_ty("Coach's Picks this week", "\n\n".join(lines) + "\n\nPaper trades: the bot buys these in its own pretend account.", "dart", "high")
    print("\n".join(lines))
    return entry


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "report"
    now = datetime.now(timezone.utc)
    if mode == "picks":
        run_picks(now, scheduled="--scheduled" in sys.argv)
    else:
        run_report(now)

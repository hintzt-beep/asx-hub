import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd
import yfinance as yf
import race
from shadow import decide as shadow_decide, holding_key
from store import get, put

TOPICS = {"Ty": os.environ.get("NTFY_TOPIC_TY", ""), "Nathan": os.environ.get("NTFY_TOPIC_NATHAN", "")}
CHECK_EVERY = 300
OLD_ALERTS = False  # old ntfy alerts are off; only bot actions are pushed

DAY_LIST = ("BHP.AX, CBA.AX, CSL.AX, WBC.AX, NAB.AX, ANZ.AX, FMG.AX, WES.AX, MQG.AX, PLS.AX, "
            "WDS.AX, TLS.AX, RIO.AX, WOW.AX, GMG.AX, STO.AX, TCL.AX, QBE.AX, ALL.AX, COL.AX, "
            "NST.AX, EVN.AX, MIN.AX, IGO.AX, LYC.AX, PDN.AX, BOE.AX, XRO.AX, WTC.AX, REA.AX")
CRYPTO_LIST = ("BTC-USD, ETH-USD, SOL-USD, XRP-USD, BNB-USD, ADA-USD, DOGE-USD, AVAX-USD, LINK-USD, DOT-USD, "
               "LTC-USD, BCH-USD")
SYD = ZoneInfo("Australia/Sydney")
MEL = ZoneInfo("Australia/Melbourne")
VOL_MULT = 2.0
RR = 2.0


def push(topic, title, msg, tags="bell", priority="default"):
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"),
        headers={"Title": title, "Tags": tags, "Priority": priority})
    urllib.request.urlopen(req, timeout=15)


def load_sent():
    today = datetime.now(MEL).strftime("%Y-%m-%d")
    data = get("system", "alerts_sent", {})
    if data.get("day") != today:
        data = {"day": today, "keys": []}
    return data


def send_once(sent, key, topic, title, msg, tags="bell", priority="default"):
    if key in sent["keys"]:
        return
    push(topic, title, msg, tags, priority)
    sent["keys"].append(key)
    print(datetime.now(MEL).strftime("%H:%M"), "SENT:", title, "-", msg)


def clean(df):
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df


def p(x):
    return f"{x:,.2f}" if x >= 1 else f"{x:,.4f}"


def asx_status():
    now = datetime.now(SYD)
    o = now.replace(hour=10, minute=0, second=0, microsecond=0)
    c = now.replace(hour=16, minute=0, second=0, microsecond=0)
    is_open = now.weekday() < 5 and o <= now < c
    mins_left = (c - now).total_seconds() / 60 if is_open else None
    return is_open, mins_left


def trend_info(ticker):
    df = yf.download(ticker, period="1y", interval="1d", progress=False)
    if df is None or len(df) < 200:
        return None, None
    return trend_score(clean(df)["Close"])


def trend_score(close):
    """Long-term trend score (0-10) and price from a series of daily closes (the last one is today)."""
    if close is None or len(close) < 200:
        return None, None
    price = float(close.iloc[-1])
    ma50 = float(close.tail(50).mean())
    ma200 = float(close.tail(200).mean())
    ma50_old = float(close.iloc[-70:-20].mean())
    month_ago = float(close.iloc[-21])
    high52 = float(close.max())
    off_high = (high52 - price) / high52 * 100
    score = 0
    score += 3 if price > ma200 else 0
    score += 2 if price > ma50 else 0
    score += 2 if ma50 > ma50_old else 0
    score += 1 if price > month_ago else 0
    score += 2 if (3 <= off_high <= 12 and price > ma200) else 0
    return score, price


def trend_word(ticker):
    score, price = trend_info(ticker)
    if score is None:
        return None, None
    word = "BUY" if score >= 7 else "HOLD" if score >= 4 else "SELL"
    return word, price


def day_setup(ticker):
    df = yf.download(ticker, period="1d", interval="5m", progress=False)
    if df is None or len(df) < 12:
        return None
    df = clean(df)
    last, prior = df.iloc[-1], df.iloc[:-1]
    day_high = float(prior["High"].max())
    avg_vol = float(prior["Volume"].mean())
    if avg_vol <= 0:
        return None
    entry = float(last["Close"])
    if entry > day_high and float(last["Volume"]) / avg_vol > VOL_MULT:
        stop = float(prior["Low"].tail(6).min())
        risk = entry - stop
        if risk <= 0:
            return None
        return entry, stop, entry + RR * risk
    return None


def last_price(ticker):
    df = yf.download(ticker, period="1d", interval="1m", progress=False)
    if df is None or len(df) == 0:
        df = yf.download(ticker, period="5d", interval="1d", progress=False)
    return float(clean(df)["Close"].iloc[-1])


# ---------- Pushes ----------
def notify_ty(title, msg, tags="robot_face", priority="default"):
    """Push a bot action to Ty's topic. A failed push never breaks a bot."""
    topic = TOPICS.get("Ty", "")
    if not topic:
        print("No Ty topic set, not sent:", title, "-", msg)
        return
    try:
        push(topic, title, msg, tags, priority)
    except Exception as e:
        print("Notify failed:", title, e)


# ---------- Shadow bot: paper mirror of Ty's real holdings. Reads them, never writes them. No real orders. ----------
LONG_LIST = ("BHP.AX, CBA.AX, CSL.AX, WES.AX, WOW.AX, TLS.AX, MQG.AX, XRO.AX, REA.AX, COL.AX, "
             "QBE.AX, TCL.AX, GMG.AX, RIO.AX, ALL.AX, WTC.AX, NAB.AX, ANZ.AX, WBC.AX, FMG.AX")
SHADOW_OWNER = "Ty"
SHADOW_FEE = 10.0
SHADOW_SLIP = 0.001


def shadow_load():
    try:
        log = get("system", "shadow_log", None)
    except Exception as e:
        print("Shadow log load failed:", e)
        return None  # never replace a saved log with a fresh one
    log = log or {}
    for k in ("sold", "sales", "buys"):
        log.setdefault(k, [])
    return log


def shadow_save(log):
    try:
        put("system", "shadow_log", log)
        return True
    except Exception as e:
        print("Shadow log save failed:", e)
        return False


def best_long_idea(exclude, score_of=None):
    """Highest-scoring BUY (score 7+) on the Long term list; the first one wins a tie. score_of(ticker) -> (score, price)."""
    best = None
    for t in [x.strip() for x in LONG_LIST.split(",")]:
        if t == exclude:
            continue
        try:
            score, _ = (score_of or trend_info)(t)
        except Exception:
            continue
        if score is not None and score >= 7 and (best is None or score > best[1]):
            best = (t, score)
    return best


def shadow_shares(proceeds, px):
    """Whole shares the shadow bot can buy with sale proceeds, after $10 brokerage and 0.1% slippage: (shares, fill)."""
    fill = px * (1 + SHADOW_SLIP)
    return math.floor((proceeds - SHADOW_FEE) / fill), fill


def shadow_reinvest(log, sale):
    """Paper-buy the best Long term idea with a sale's proceeds, less $10 brokerage and 0.1% slippage."""
    idea = best_long_idea(sale["ticker"])
    if idea is None:
        if not sale.get("no_idea_sent"):
            sale["no_idea_sent"] = True
            if shadow_save(log):
                notify_ty(f"SHADOW: no BUY idea after selling {sale['ticker']}",
                             f"No Long term idea scores BUY right now. Holding ${sale['proceeds']:,.2f} paper cash until one does.", "hourglass")
        return
    ticker, score = idea
    px = last_price(ticker)
    shares, fill = shadow_shares(sale["proceeds"], px)
    if shares < 1:
        sale["reinvested"], sale["note"] = True, "Proceeds too small to buy one share."
        if shadow_save(log):
            notify_ty(f"SHADOW: no buy after selling {sale['ticker']}", sale["note"], "warning")
        return
    cost = shares * fill + SHADOW_FEE
    buy = {"ticker": ticker, "shares": shares, "price": fill, "price_px": px, "brokerage": SHADOW_FEE, "cost": cost,
           "costs": SHADOW_FEE + shares * (fill - px), "score": score, "mark": px, "sale_key": sale["key"],
           "date": datetime.now(MEL).strftime("%Y-%m-%d %H:%M")}
    log["buys"].append(buy)
    sale["reinvested"] = True
    if not shadow_save(log):
        log["buys"].pop()
        sale["reinvested"] = False
        return
    notify_ty(f"SHADOW BUY {ticker}", f"Paper bought {shares} at ${p(fill)} (cost ${cost:,.2f} incl. $10 brokerage). "
                 f"Best Long term idea, score {score}. Bought with the proceeds from selling {sale['ticker']}.", "green_circle", "high")


def shadow_check_holding(log, h):
    tk = h.get("ticker")
    qty, paid = float(h.get("qty") or 0), float(h.get("paid") or 0)
    if not tk or qty <= 0 or paid <= 0:
        return  # nothing to judge without what was paid
    key = holding_key(h)
    if key in log["sold"]:
        return  # already paper-sold once; never log the same sale twice
    score, _ = trend_info(tk)
    if score is None:
        return
    price = last_price(tk)
    dec = shadow_decide(qty, paid, price, score, h.get("bought"))
    if dec["word"] != "SELL":
        return
    sale = {"key": key, "ticker": tk, "qty": qty, "paid": paid, "bought": h.get("bought"), "price": price,
            "date": datetime.now(MEL).strftime("%Y-%m-%d %H:%M"), "reason": dec["reason"], "costs": SHADOW_FEE,
            "proceeds": qty * price - SHADOW_FEE, "gain": dec["gain"], "pct": dec["pct"], "reinvested": False}
    log["sold"].append(key)
    log["sales"].append(sale)
    if not shadow_save(log):
        log["sold"].pop()
        log["sales"].pop()
        return
    notify_ty(f"SHADOW SELL {tk}", f"Paper sold {qty:g} at ${p(price)}. {dec['reason']}", "red_circle", "urgent")


def shadow_run():
    log = shadow_load()
    if log is None:
        return
    try:
        holdings = get(SHADOW_OWNER, "holdings", [])  # read only
    except Exception as e:
        print("Shadow holdings load failed:", e)
        return
    for h in holdings:
        try:
            shadow_check_holding(log, h)
        except Exception as e:
            print("Shadow check failed:", h.get("ticker"), e)
    for sale in log["sales"]:
        if not sale.get("reinvested"):
            try:
                shadow_reinvest(log, sale)
            except Exception as e:
                print("Shadow buy failed:", sale.get("ticker"), e)
    for b in log["buys"]:
        try:
            b["mark"] = last_price(b["ticker"])
        except Exception:
            pass
    if log["sales"] or log["buys"]:
        shadow_save(log)


def check_user(sent, user, topic, asx_open, mins_left):
    # 1. Things you own
    for h in get(user, "holdings", []):
        try:
            word, price = trend_word(h["ticker"])
            if word == "SELL":
                send_once(sent, f"{user}-hold-sell-{h['ticker']}", topic, f"SELL {h['ticker']}",
                          f"You own {h['qty']:g}. Price ${p(price)}. It is trending down. Think about selling.",
                          "red_circle", "high")
        except Exception as e:
            print("Holding check failed:", user, h, e)

    # 2. Trades logged today
    log = pd.DataFrame(get(user, "trades", []))
    if len(log) and "time" in log.columns:
        today = datetime.now(MEL).strftime("%Y-%m-%d")
        log = log[log["time"].astype(str).str.startswith(today)]
        for _, r in log.iterrows():
            try:
                t = r["ticker"]
                now_p = last_price(t)
                stop = pd.to_numeric(r.get("stop"), errors="coerce")
                target = pd.to_numeric(r.get("target"), errors="coerce")
                if pd.notna(target) and now_p >= target:
                    send_once(sent, f"{user}-target-{t}", topic, f"SELL {t}: target hit",
                              f"Now ${p(now_p)}. Take the profit.", "moneybag", "high")
                elif pd.notna(stop) and now_p <= stop:
                    send_once(sent, f"{user}-stop-{t}", topic, f"SELL {t}: stop hit",
                              f"Now ${p(now_p)}. Get out to keep the loss small.", "red_circle", "urgent")
                elif r["type"] == "day" and asx_open and mins_left is not None and mins_left < 15:
                    send_once(sent, f"{user}-close-{t}", topic, f"SELL {t}: ASX closing",
                              f"Under 15 minutes left. Now ${p(now_p)}. Close the day trade.", "alarm_clock", "high")
            except Exception as e:
                print("Trade check failed:", user, r.get("ticker"), e)


def check():
    sent = load_sent()
    asx_open, mins_left = asx_status()
    users = {u: t for u, t in TOPICS.items() if t and OLD_ALERTS}
    try:
        for user, topic in users.items():
            check_user(sent, user, topic, asx_open, mins_left)

        shadow_run()
        race.run(notify_ty, asx_open)  # paper bot race, pretend money only

        # 3. New BUY setups, sent to everyone (old alerts only)
        names = []
        if users and asx_open:
            names += [t.strip() for t in DAY_LIST.split(",")]
        if users:
            names += [t.strip() for t in CRYPTO_LIST.split(",")]
        for t in names:
            try:
                s = day_setup(t)
                if s:
                    entry, stop, target = s
                    for user, topic in users.items():
                        send_once(sent, f"{user}-buy-{t}", topic, f"BUY {t}",
                                  f"Breaking out. Buy at about ${p(entry)}. Sell if it drops to ${p(stop)} or rises to ${p(target)}.",
                                  "green_circle", "high")
            except Exception as e:
                print("Scan failed:", t, e)
    finally:
        put("system", "alerts_sent", sent)


if __name__ == "__main__":
    if "--once" in sys.argv:
        check()
    else:
        print("Alerts running. Control C to stop.")
        while True:
            try:
                check()
            except Exception as e:
                print("Check failed:", e)
            time.sleep(CHECK_EVERY)
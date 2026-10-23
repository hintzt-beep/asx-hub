import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd
import yfinance as yf
from store import get, put

TOPICS = {"Ty": os.environ.get("NTFY_TOPIC_TY", ""), "Nathan": os.environ.get("NTFY_TOPIC_NATHAN", "")}
CHECK_EVERY = 300

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


def trend_word(ticker):
    df = yf.download(ticker, period="1y", interval="1d", progress=False)
    if df is None or len(df) < 200:
        return None, None
    close = clean(df)["Close"]
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


# ---------- Paper trading: pretend money only. No real orders, ever. ----------
PAPER_START = 10000.0
PAPER_FEE = 10.0       # brokerage on each buy and each sell
PAPER_SLIP = 0.001     # 0.1% against us on every fill
PAPER_RISK = 0.01      # loss at the stop = 1% of account value
PAPER_MAX_POS = 0.20   # max 20% of the account in one position


def paper_load():
    try:
        acct = get("system", "paper_account", None)
    except Exception as e:
        print("Paper account load failed:", e)
        return None  # never replace a saved account with a fresh one
    if not acct:
        acct = {"start": PAPER_START, "cash": PAPER_START, "positions": [], "closed": [], "signals": {}}
    today = datetime.now(MEL).strftime("%Y-%m-%d")
    if acct.get("signals", {}).get("day") != today:
        acct["signals"] = {"day": today, "keys": []}
    return acct


def paper_save(acct):
    if acct is None:
        return
    try:
        put("system", "paper_account", acct)
    except Exception as e:
        print("Paper account save failed:", e)


def paper_value(acct):
    return acct["cash"] + sum(x["shares"] * x.get("mark", x["entry"]) for x in acct["positions"])


def paper_open(acct, ticker, entry, stop, target, asx_open, mins_left):
    if acct is None:
        return
    try:
        is_asx = ticker.endswith(".AX")
        if is_asx and (not asx_open or mins_left is None or mins_left < 15):
            return  # would be force-closed straight away
        key = f"buy-{ticker}"  # one paper buy per ticker per day, like the alerts
        if key in acct["signals"]["keys"] or any(x["ticker"] == ticker for x in acct["positions"]):
            return
        fill = entry * (1 + PAPER_SLIP)
        risk = fill - stop * (1 - PAPER_SLIP)  # loss per share if the stop fills
        if risk <= 0:
            return
        shares = min((paper_value(acct) * PAPER_RISK - 2 * PAPER_FEE) / risk,
                     paper_value(acct) * PAPER_MAX_POS / fill,
                     (acct["cash"] - PAPER_FEE) / fill)
        shares = math.floor(shares) if is_asx else math.floor(shares * 1e6) / 1e6
        if shares <= 0:
            return
        acct["cash"] -= shares * fill + PAPER_FEE
        acct["positions"].append({"ticker": ticker, "type": "day" if is_asx else "crypto",
                                  "opened": datetime.now(timezone.utc).isoformat(), "entry_px": entry,
                                  "entry": fill, "shares": shares, "stop": stop, "target": target, "mark": entry})
        acct["signals"]["keys"].append(key)
        print(datetime.now(MEL).strftime("%H:%M"), f"PAPER BUY {ticker}: {shares:g} at ${p(fill)}")
    except Exception as e:
        print("Paper open failed:", ticker, e)


def paper_close(acct, pos, px, reason):
    fill = px * (1 - PAPER_SLIP)
    proceeds = pos["shares"] * fill - PAPER_FEE
    slip = pos["shares"] * (pos["entry"] - pos["entry_px"]) + pos["shares"] * (px - fill)
    pnl = proceeds - (pos["shares"] * pos["entry"] + PAPER_FEE)
    acct["cash"] += proceeds
    acct["positions"].remove(pos)
    acct["closed"].append({"ticker": pos["ticker"], "entry": round(pos["entry"], 6), "exit": round(fill, 6),
                           "shares": pos["shares"], "costs": round(2 * PAPER_FEE + slip, 2),
                           "pnl": round(pnl, 2), "reason": reason, "opened": pos["opened"],
                           "closed": datetime.now(timezone.utc).isoformat()})
    print(datetime.now(MEL).strftime("%H:%M"), f"PAPER SELL {pos['ticker']} ({reason}): P/L ${pnl:,.2f}")


def paper_hit(pos, now_p):
    """Stop or target touched since the position opened? Stop wins if both in one bar."""
    df = yf.download(pos["ticker"], period="5d", interval="5m", progress=False)
    if df is not None and len(df):
        df = clean(df)
        for _, r in df[df.index > pd.Timestamp(pos["opened"])].iterrows():
            if float(r["Low"]) <= pos["stop"]:
                return "stop", min(pos["stop"], float(r["Open"]))
            if float(r["High"]) >= pos["target"]:
                return "target", max(pos["target"], float(r["Open"]))
    if now_p <= pos["stop"]:
        return "stop", now_p
    if now_p >= pos["target"]:
        return "target", now_p
    return None


def paper_manage(acct, asx_open, mins_left):
    if acct is None:
        return
    for pos in list(acct["positions"]):
        try:
            now_p = last_price(pos["ticker"])
            pos["mark"] = now_p
            hit = paper_hit(pos, now_p)
            if hit:
                paper_close(acct, pos, hit[1], hit[0])
            elif pos["type"] == "day" and (not asx_open or (mins_left is not None and mins_left < 15)):
                paper_close(acct, pos, now_p, "ASX close")
        except Exception as e:
            print("Paper manage failed:", pos.get("ticker"), e)


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
    paper = paper_load()
    users = {u: t for u, t in TOPICS.items() if t}
    try:
        for user, topic in users.items():
            check_user(sent, user, topic, asx_open, mins_left)

        paper_manage(paper, asx_open, mins_left)

        # 3. New BUY setups, sent to everyone
        names = []
        if asx_open:
            names += [t.strip() for t in DAY_LIST.split(",")]
        names += [t.strip() for t in CRYPTO_LIST.split(",")]
        for t in names:
            try:
                s = day_setup(t)
                if s:
                    entry, stop, target = s
                    paper_open(paper, t, entry, stop, target, asx_open, mins_left)
                    for user, topic in users.items():
                        send_once(sent, f"{user}-buy-{t}", topic, f"BUY {t}",
                                  f"Breaking out. Buy at about ${p(entry)}. Sell if it drops to ${p(stop)} or rises to ${p(target)}.",
                                  "green_circle", "high")
            except Exception as e:
                print("Scan failed:", t, e)
    finally:
        put("system", "alerts_sent", sent)
        paper_save(paper)


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
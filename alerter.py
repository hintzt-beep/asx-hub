import os
import sys
import time
import urllib.request
from datetime import datetime
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
    users = {u: t for u, t in TOPICS.items() if t}
    try:
        for user, topic in users.items():
            check_user(sent, user, topic, asx_open, mins_left)

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
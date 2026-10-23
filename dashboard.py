import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import json
import urllib.request
from streamlit_autorefresh import st_autorefresh
from store import get, put

st.set_page_config(page_title="Hub", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

USERS = {"Ty": os.environ.get("TY_PASSWORD", "change-me-ty"),
         "Nathan": os.environ.get("NATHAN_PASSWORD", "change-me-nathan")}

GREEN, RED, AMBER, GREY = "#22C55E", "#EF4444", "#F59E0B", "#8A94A6"
WORD_COLOR = {"BUY": GREEN, "SELL": RED, "HOLD": AMBER}
MEL = ZoneInfo("Australia/Melbourne")

st.markdown("""
<style>
#MainMenu, footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}
.block-container {padding: 1.2rem 1rem 4rem;}
@media (min-width: 768px) {.block-container {padding: 2rem 3rem 4rem;}}
.card {background: #151A23; border: 1px solid #232A36; border-radius: 18px; padding: 14px 16px; margin-bottom: 10px;}
.hero {background: linear-gradient(135deg, #7C5CFF40, #00D9FF26); border: 1px solid #7C5CFF66; border-radius: 22px; padding: 18px; margin-bottom: 12px;}
.big {font-size: 2.2rem; font-weight: 800; line-height: 1.1;}
.sub {color: #8A94A6; font-size: 0.8rem;}
.row {display: flex; justify-content: space-between; align-items: center; gap: 8px;}
.word {padding: 4px 12px; border-radius: 999px; font-weight: 800; font-size: 0.8rem; letter-spacing: 0.08em;}
.chips {display: flex; gap: 6px; overflow-x: auto; margin-bottom: 12px; padding-bottom: 2px;}
.chip {flex: 0 0 auto; background: #151A23; border: 1px solid #232A36; border-radius: 999px; padding: 6px 12px; font-size: 0.75rem; white-space: nowrap;}
.dot {display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px;}
.stButton button {border-radius: 12px; width: 100%; min-height: 46px; font-weight: 700;}
button[data-baseweb="tab"] {font-size: 0.95rem; font-weight: 700;}
div[data-baseweb="input"], div[data-baseweb="select"] > div {border-radius: 12px;}
h4 {margin: 14px 0 6px;}
</style>
""", unsafe_allow_html=True)

# ---------- Login ----------
if "user" not in st.session_state:
    st.markdown('<div class="hero"><div class="big">Hub</div><div class="sub">Your money, made simple.</div></div>', unsafe_allow_html=True)
    who = st.radio("Who are you?", list(USERS), horizontal=True)
    pw = st.text_input("Password", type="password")
    if st.button("Log in", type="primary"):
        if pw == USERS[who]:
            st.session_state.user = who
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()

USER = st.session_state.user
st_autorefresh(interval=120000, key="refresh")

DAY_LIST = ("BHP.AX, CBA.AX, CSL.AX, WBC.AX, NAB.AX, ANZ.AX, FMG.AX, WES.AX, MQG.AX, PLS.AX, "
            "WDS.AX, TLS.AX, RIO.AX, WOW.AX, GMG.AX, STO.AX, TCL.AX, QBE.AX, ALL.AX, COL.AX, "
            "NST.AX, EVN.AX, MIN.AX, IGO.AX, LYC.AX, PDN.AX, BOE.AX, XRO.AX, WTC.AX, REA.AX")
LONG_LIST = ("BHP.AX, CBA.AX, CSL.AX, WES.AX, WOW.AX, TLS.AX, MQG.AX, XRO.AX, REA.AX, COL.AX, "
             "QBE.AX, TCL.AX, GMG.AX, RIO.AX, ALL.AX, WTC.AX, NAB.AX, ANZ.AX, WBC.AX, FMG.AX")
CRYPTO_LIST = "BTC-USD, ETH-USD, SOL-USD, XRP-USD, BNB-USD, ADA-USD, DOGE-USD, AVAX-USD, LINK-USD, DOT-USD, LTC-USD, BCH-USD"
CELEB_URL = "https://www.bargo.ai/free-apis/congress/v1/trades?limit=40"
COLS = ["time", "type", "ticker", "entry", "shares", "dollars", "score", "stop", "target"]
POT_OF = {"day": "day", "long": "long", "crypto_day": "crypto", "crypto_long": "crypto"}
POT_NAME = {"day": "Day trading", "long": "Long term", "crypto": "Crypto"}

# ---------- Saved data (Supabase) ----------
def load_json(name, default):
    return get(USER, name, default)

def save_json(name, data):
    put(USER, name, data)

pots = load_json("pots", {"day": 0.0, "long": 0.0, "crypto": 0.0})
holdings = load_json("holdings", [])
watchlist = load_json("watchlist", [])
log_df = pd.DataFrame(load_json("trades", []), columns=COLS)
for c in ["entry", "shares", "dollars"]:
    log_df[c] = pd.to_numeric(log_df[c], errors="coerce")

def used(pot):
    if len(log_df) == 0:
        return 0.0
    mask = log_df["type"].map(POT_OF) == pot
    return float(pd.to_numeric(log_df.loc[mask, "dollars"], errors="coerce").fillna(0).sum())

cash = {k: max(pots[k] - used(k), 0.0) for k in pots}

# ---------- Helpers ----------
def clean(df):
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df

def pill(word):
    c = WORD_COLOR.get(word, GREY)
    return f'<span class="word" style="background:{c}22; color:{c}; border:1px solid {c}66;">{word}</span>'

def money(x):
    c = GREEN if x > 0 else RED if x < 0 else GREY
    s = "+" if x > 0 else "-" if x < 0 else ""
    return f'<b style="color:{c}">{s}${abs(x):,.2f}</b>'

def fp(x):
    return f"{x:,.2f}" if x >= 1 else f"{x:,.4f}"

def card(title, word, body):
    st.markdown(f'<div class="card"><div class="row"><b style="font-size:1.1rem">{title}</b>{pill(word)}</div>{body}</div>', unsafe_allow_html=True)

def line(left, right):
    return f'<div class="row" style="margin-top:6px"><span class="sub">{left}</span><span>{right}</span></div>'

def fmt_left(sec):
    h, m = int(sec // 3600), int(sec % 3600 // 60)
    return f"{h // 24}d {h % 24}h" if h >= 24 else f"{h}h {m}m"

def market_status(tz, oh, om, ch, cm):
    zone = ZoneInfo(tz)
    now = datetime.now(zone)
    o = now.replace(hour=oh, minute=om, second=0, microsecond=0)
    c = now.replace(hour=ch, minute=cm, second=0, microsecond=0)
    if now.weekday() < 5 and o <= now < c:
        return True, c.timestamp() - now.timestamp()
    nxt = o
    if now >= o or now.weekday() >= 5:
        nxt = (o.replace(tzinfo=None) + timedelta(days=1)).replace(tzinfo=zone)
    while nxt.weekday() >= 5:
        nxt = (nxt.replace(tzinfo=None) + timedelta(days=1)).replace(tzinfo=zone)
    return False, nxt.timestamp() - now.timestamp()

def scan_day(ticker, pot, whole):
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
    if entry > day_high and float(last["Volume"]) / avg_vol > 2:
        stop = float(prior["Low"].tail(6).min())
        risk = entry - stop
        if risk <= 0:
            return None
        qty = min(pot * 0.01 / risk, pot * 0.20 / entry)
        qty = int(qty) if whole else round(qty, 6)
        return {"ticker": ticker, "entry": entry, "stop": stop, "target": entry + 2 * risk,
                "shares": qty, "dollars": qty * entry, "score": round(float(last["Volume"]) / avg_vol, 1)}
    return None

@st.cache_data(ttl=900)
def scan_long(ticker):
    df = yf.download(ticker, period="1y", interval="1d", progress=False)
    if df is None or len(df) < 200:
        return None
    close = clean(df)["Close"]
    price = float(close.iloc[-1])
    ma50, ma200 = float(close.tail(50).mean()), float(close.tail(200).mean())
    ma50_old = float(close.iloc[-70:-20].mean())
    mom = (price - float(close.iloc[-21])) / float(close.iloc[-21]) * 100
    off_high = (float(close.max()) - price) / float(close.max()) * 100
    score, why = 0, []
    if price > ma200:
        score += 3
        why.append("long-term uptrend")
    else:
        why.append("long-term downtrend")
    if price > ma50:
        score += 2
    if ma50 > ma50_old:
        score += 2
        why.append("getting stronger")
    if mom > 0:
        score += 1
    why.append(f"{'up' if mom > 0 else 'down'} {abs(mom):.1f}% this month")
    if 3 <= off_high <= 12 and price > ma200:
        score += 2
        why.append("a little below its high, a good entry")
    return {"ticker": ticker, "price": price, "score": score, "why": ", ".join(why)}

def long_word(score):
    return "BUY" if score >= 7 else "HOLD" if score >= 4 else "SELL"

@st.cache_data(ttl=60)
def live_price(ticker):
    try:
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        if df is None or len(df) == 0:
            df = yf.download(ticker, period="5d", interval="1d", progress=False)
        return float(clean(df)["Close"].iloc[-1])
    except Exception:
        return None

@st.cache_data(ttl=900)
def watch_signal(ticker):
    try:
        return scan_long(ticker)
    except Exception:
        return None

@st.cache_data(ttl=21600)
def celeb_trades():
    req = urllib.request.Request(CELEB_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    if isinstance(data, dict):
        for k in ["trades", "data", "results", "items"]:
            if isinstance(data.get(k), list):
                return data[k]
        return []
    return data if isinstance(data, list) else []

def pick(d, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            if isinstance(v, dict):
                v = v.get("name") or v.get("full_name") or ""
            return v
    return ""

def log_trade(row):
    row = {k: row.get(k, "") for k in COLS}
    rows = load_json("trades", [])
    rows.append(row)
    save_json("trades", rows)

def trade_word(r, asx_closing):
    now_p = float(r["now"])
    stop = pd.to_numeric(r.get("stop"), errors="coerce")
    target = pd.to_numeric(r.get("target"), errors="coerce")
    if pd.notna(target) and now_p >= target:
        return "SELL", "Target hit. Take the profit."
    if pd.notna(stop) and now_p <= stop:
        return "SELL", "Dropped to your stop. Get out."
    if r["type"] == "day" and asx_closing:
        return "SELL", "ASX closes soon. Close the day trade."
    return "HOLD", "Still on track."

def bought_row(key, kind, ticker, price, qty, whole, stop="", target=""):
    with st.expander(f"I bought {ticker}"):
        fill = st.number_input("Price I paid ($)", min_value=0.0, value=float(price), format="%.4f", key=f"f{key}")
        got = st.number_input("How many", min_value=0.0, value=float(qty), step=1.0 if whole else 0.0001,
                              format="%.0f" if whole else "%.6f", key=f"q{key}")
        if st.button("Save", key=f"s{key}", type="primary"):
            log_trade({"time": datetime.now(MEL).strftime("%Y-%m-%d %H:%M"), "type": kind, "ticker": ticker,
                       "entry": fill, "shares": got, "dollars": round(fill * got, 2), "stop": stop, "target": target})
            st.success("Saved. You'll get a ping when it's time to sell.")

# ---------- Markets ----------
now = datetime.now(MEL)
chips, asx_open, asx_closing = "", False, False
for name, tz, oh, om, ch, cm in [("ASX", "Australia/Sydney", 10, 0, 16, 0),
                                 ("TSX", "America/Toronto", 9, 30, 16, 0),
                                 ("NYSE", "America/New_York", 9, 30, 16, 0)]:
    is_open, left = market_status(tz, oh, om, ch, cm)
    if name == "ASX":
        asx_open, asx_closing = is_open, is_open and left < 900
    local = datetime.now(ZoneInfo(tz)).strftime("%H:%M")
    word = "closes" if is_open else "opens"
    chips += f'<div class="chip"><span class="dot" style="background:{GREEN if is_open else GREY}"></span><b>{name}</b> {local} · {word} in {fmt_left(left)}</div>'
chips += f'<div class="chip"><span class="dot" style="background:{GREEN}"></span><b>Crypto</b> always open</div>'

# ---------- Today's trades and alerts ----------
pnl = pd.DataFrame()
if len(log_df):
    t = log_df[log_df["time"].astype(str).str.startswith(now.strftime("%Y-%m-%d"))].copy()
    if len(t):
        t["now"] = t["ticker"].apply(live_price)
        pnl = t.dropna(subset=["now", "entry", "shares"]).copy()
        pnl["gl"] = (pnl["now"] - pnl["entry"]) * pnl["shares"]
total_pl = float(pnl["gl"].sum()) if len(pnl) else 0.0
ups = int((pnl["gl"] > 0).sum()) if len(pnl) else 0
downs = int((pnl["gl"] < 0).sum()) if len(pnl) else 0

alerts, hold_info = [], []
for h in holdings:
    try:
        r = scan_long(h["ticker"])
    except Exception:
        r = None
    w = long_word(r["score"]) if r else "HOLD"
    hold_info.append((h, r, w))
    if w == "SELL":
        alerts.append(("SELL", h["ticker"], "Trending down. Think about selling."))
for _, r in pnl.iterrows():
    w, why = trade_word(r, asx_closing)
    if w == "SELL":
        alerts.append(("SELL", r["ticker"], why))

# ---------- Top of screen ----------
top_l, top_r = st.columns([3, 1])
top_l.markdown(f'<div class="sub" style="padding-top:10px">{now.strftime("%a %d %b, %H:%M")}</div>', unsafe_allow_html=True)
if top_r.button("Log out"):
    del st.session_state["user"]
    st.rerun()
st.markdown(f'<div class="chips">{chips}</div>', unsafe_allow_html=True)

home, port, watch, ideas, celebs = st.tabs(["Home", "Portfolio", "Watchlist", "Ideas", "Celebs"])

# ---------- Home ----------
with home:
    total = sum(pots.values())
    st.markdown(f'<div class="hero"><div class="sub">Hi {USER}</div><div class="big">${total:,.0f}</div>'
                f'<div class="sub">in your pots</div><div style="margin-top:10px">Today {money(total_pl)} '
                f'<span class="sub">&nbsp;{ups} up · {downs} down</span></div></div>', unsafe_allow_html=True)
    st.markdown("#### Needs you")
    if alerts:
        for w, tk, why in alerts:
            card(tk, w, f'<div class="sub" style="margin-top:6px">{why}</div>')
    else:
        st.markdown('<div class="card sub">All good. Nothing needs you right now.</div>', unsafe_allow_html=True)
    st.markdown("#### Your pots")
    boxes = "".join(f'<div class="card" style="flex:1; margin:0"><div class="sub">{POT_NAME[k]}</div>'
                     f'<b>${pots[k]:,.0f}</b><div class="sub">${cash[k]:,.0f} free</div></div>' for k in pots)
    st.markdown(f'<div class="row" style="align-items:stretch">{boxes}</div>', unsafe_allow_html=True)
    with st.expander("Add or take out money"):
        which = st.selectbox("Pot", list(pots), format_func=lambda k: POT_NAME[k])
        amt = st.number_input("Amount ($)", 0.0, 10000000.0, 0.0, 100.0)
        b1, b2 = st.columns(2)
        if b1.button("Add", type="primary"):
            pots[which] += amt
            save_json("pots", pots)
            st.rerun()
        if b2.button("Take out"):
            pots[which] = max(pots[which] - amt, 0.0)
            save_json("pots", pots)
            st.rerun()

# ---------- Portfolio ----------
with port:
    st.markdown("#### What you own")
    with st.expander("Add something you own"):
        new_t = st.text_input("Code (like BHP, or BTC-USD for crypto)")
        new_q = st.number_input("How many", min_value=0.0, value=0.0)
        if st.button("Add it", type="primary") and new_t.strip() and new_q > 0:
            tk = new_t.strip().upper()
            if "." not in tk and "-" not in tk:
                tk += ".AX"
            holdings.append({"ticker": tk, "qty": new_q})
            save_json("holdings", holdings)
            st.rerun()
    if not holdings:
        st.markdown('<div class="card sub">Nothing added yet.</div>', unsafe_allow_html=True)
    plain = {"BUY": "Looking strong. Fine to buy more.", "HOLD": "Keep it.", "SELL": "Trending down. Think about selling."}
    for i, (h, r, w) in enumerate(hold_info):
        if r:
            body = line("Price", f"${fp(r['price'])}") + line("Worth", f"${r['price'] * h['qty']:,.0f}")
            body += f'<div class="sub" style="margin-top:8px">{plain[w]} ({r["why"]})</div>'
        else:
            body = '<div class="sub" style="margin-top:6px">No data. Check the code.</div>'
        card(f'{h["ticker"]} <span class="sub">x{h["qty"]:g}</span>', w, body)
        if st.button(f"Remove {h['ticker']}", key=f"rm{i}"):
            holdings.pop(i)
            save_json("holdings", holdings)
            st.rerun()
    st.markdown("#### Bought today")
    if len(pnl) == 0:
        st.markdown('<div class="card sub">Nothing bought today.</div>', unsafe_allow_html=True)
    for idx, r in pnl.iterrows():
        w, why = trade_word(r, asx_closing)
        body = line("Paid", f"${fp(float(r['entry']))}") + line("Now", f"${fp(float(r['now']))}") + line("Gain / loss", money(r["gl"]))
        card(r["ticker"], w, body + f'<div class="sub" style="margin-top:8px">{why}</div>')
        if st.button(f"Remove {r['ticker']}", key=f"rmt{idx}"):
            rows = load_json("trades", [])
            hit = next((j for j, x in enumerate(rows) if x.get("time") == r["time"] and x.get("ticker") == r["ticker"]), None)
            if hit is not None:
                rows.pop(hit)
                save_json("trades", rows)
            st.rerun()
    if len(log_df):
        if not st.session_state.get("confirm_clear"):
            if st.button("Clear all test trades"):
                st.session_state.confirm_clear = True
                st.rerun()
        else:
            st.warning(f"This deletes all {len(log_df)} trades in your history and frees the money they used. It cannot be undone.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, delete all", type="primary"):
                save_json("trades", [])
                st.session_state.confirm_clear = False
                st.rerun()
            if c2.button("Cancel"):
                st.session_state.confirm_clear = False
                st.rerun()
    with st.expander("Full trade history"):
        st.dataframe(log_df, use_container_width=True)

# ---------- Watchlist ----------
with watch:
    st.markdown("#### Watchlist")
    with st.expander("Add a ticker"):
        wt = st.text_input("Code (like BHP, or BTC-USD for crypto)", key="watch_in")
        if st.button("Add to watchlist", type="primary"):
            tk = wt.strip().upper()
            if tk and "." not in tk and "-" not in tk:
                tk += ".AX"
            if tk and tk not in watchlist:
                watchlist.append(tk)
                save_json("watchlist", watchlist)
                st.rerun()
    if not watchlist:
        st.markdown('<div class="card sub">Nothing on your watchlist yet.</div>', unsafe_allow_html=True)
    plain_w = {"BUY": "Looking strong.", "HOLD": "Nothing to do.", "SELL": "Trending down."}
    for i, tk in enumerate(watchlist):
        r = watch_signal(tk)
        if r:
            w = long_word(r["score"])
            body = line("Price", f"${fp(r['price'])}")
            body += f'<div class="sub" style="margin-top:8px">{plain_w[w]} ({r["why"]})</div>'
        else:
            w, body = "HOLD", '<div class="sub" style="margin-top:6px">No data. Check the code.</div>'
        card(tk, w, body)
        if st.button(f"Remove {tk}", key=f"wrm{i}"):
            watchlist.pop(i)
            save_json("watchlist", watchlist)
            st.rerun()

# ---------- Ideas ----------
with ideas:
    market = st.radio("Market", ["Shares", "Crypto"], horizontal=True)
    style = st.radio("Style", ["Today", "Long term"], horizontal=True)
    crypto, today = market == "Crypto", style == "Today"
    pot_key = "crypto" if crypto else "day" if today else "long"
    kind = ("crypto_" if crypto else "") + ("day" if today else "long")
    names = [x.strip() for x in (CRYPTO_LIST if crypto else DAY_LIST if today else LONG_LIST).split(",")]
    unit, whole = ("coins", False) if crypto else ("shares", True)
    key = f"ideas_{kind}"
    if today and not crypto and not asx_open:
        st.markdown('<div class="card sub">The ASX is closed. Today ideas work while it is open.</div>', unsafe_allow_html=True)
    if st.button("Find ideas", type="primary"):
        found, bar = [], st.progress(0)
        for i, tk in enumerate(names):
            try:
                r = scan_day(tk, cash[pot_key], whole) if today else scan_long(tk)
                if r and (today or long_word(r["score"]) == "BUY"):
                    found.append(r)
            except Exception:
                pass
            bar.progress((i + 1) / len(names))
        bar.empty()
        st.session_state[key] = sorted(found, key=lambda x: -x["score"])
    items = st.session_state.get(key)
    if items == []:
        st.markdown('<div class="card sub">Nothing worth buying right now. Waiting is fine.</div>', unsafe_allow_html=True)
    for n, s in enumerate(items or []):
        if today:
            body = (line("Buy", f"{s['shares']} {unit} (${s['dollars']:,.0f})") + line("At about", f"${fp(s['entry'])}")
                    + line("Sell if it drops to", f"${fp(s['stop'])}") + line("Sell if it rises to", f"${fp(s['target'])}"))
            if s["shares"] == 0:
                body += '<div class="sub" style="margin-top:8px">Add money to this pot on Home to get a size.</div>'
            card(s["ticker"], "BUY", body)
            bought_row(f"{kind}{n}", kind, s["ticker"], s["entry"], s["shares"], whole, s["stop"], s["target"])
        else:
            dollars = cash[pot_key] * 0.10
            qty = int(dollars // s["price"]) if whole else round(dollars / s["price"], 6)
            body = line("Price", f"${fp(s['price'])}") + line("Put in", f"${qty * s['price']:,.0f} ({qty} {unit})")
            card(s["ticker"], "BUY", body + f'<div class="sub" style="margin-top:8px">{s["why"].capitalize()}.</div>')
            bought_row(f"{kind}{n}", kind, s["ticker"], s["price"], qty, whole)

# ---------- Celebs ----------
with celebs:
    st.markdown('<div class="sub">US politicians\' trades from public filings, reported days or weeks later. Data: Bargo Congress Trades.</div>', unsafe_allow_html=True)
    try:
        trades = celeb_trades()
    except Exception as e:
        trades = []
        st.warning(f"Couldn't load right now: {e}")
    for t in trades[:40]:
        if not isinstance(t, dict):
            continue
        who = pick(t, "member", "member_name", "name", "politician", "representative", "senator")
        tick = pick(t, "ticker", "symbol")
        kind_txt = str(pick(t, "type", "transaction_type", "transaction", "side")).lower()
        chamber = str(pick(t, "chamber", "house", "body")).lower()
        party = str(pick(t, "party", "party_name"))
        party = {"R": "Republican", "D": "Democrat", "I": "Independent"}.get(party.upper(), party)
        state = str(pick(t, "state", "state_name", "state_code"))
        role = "Senator" if "sen" in chamber else "House member" if ("house" in chamber or "rep" in chamber) else "US politician"
        tag = ", ".join(x for x in [role, party, state] if x)
        w = "BUY" if ("purchase" in kind_txt or "buy" in kind_txt) else "SELL" if ("sale" in kind_txt or "sell" in kind_txt) else "HOLD"
        body = f'<div class="sub" style="margin-top:4px">{who} ({tag})</div>'
        body += line("Amount", pick(t, "amount", "amount_range", "range")) + line("Date", pick(t, "transaction_date", "traded", "trade_date", "date"))
        card(tick or "?", w, body)
    if trades:
        with st.expander("Raw data (for fixing)"):
            st.json(trades[0])

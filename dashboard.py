import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os
import json
import urllib.request
from streamlit_autorefresh import st_autorefresh
from store import get, put
from shadow import decide, holding_key
import plotly.graph_objects as go
import race
from bots import STYLES

st.set_page_config(page_title="Hub", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

ADMIN_PASSWORD = os.environ.get("TY_PASSWORD", "change-me-ty")
OWNER = "Ty"  # Supabase owner key for Admin's saved data (kept so existing data still loads)

GREEN, RED, AMBER, GREY = "#22C55E", "#EF4444", "#F59E0B", "#8A94A6"
WORD_COLOR = {"BUY": GREEN, "SELL": RED, "HOLD": AMBER}
MEL = ZoneInfo("Australia/Melbourne")

# Original angular robot-bear head, one glowing red eye (inline SVG).
BEAR_SVG = ('<svg width="56" height="56" viewBox="0 0 64 64" fill="none" stroke-linejoin="miter" role="img" aria-label="Robot bear">'
            '<polygon points="6,13 12,6 22,6 27,13 22,22 10,22" fill="#16181C" stroke="#3A3F47" stroke-width="1.6"/>'
            '<polygon points="58,13 52,6 42,6 37,13 42,22 54,22" fill="#16181C" stroke="#3A3F47" stroke-width="1.6"/>'
            '<polygon points="12,13 15,10 19,10 21,14 18,18 13,18" fill="#0A0A0C" stroke="#3A3F47" stroke-width="1"/>'
            '<polygon points="52,13 49,10 45,10 43,14 46,18 51,18" fill="#0A0A0C" stroke="#3A3F47" stroke-width="1"/>'
            '<polygon points="13,22 22,12 42,12 51,22 51,43 41,55 23,55 13,43" fill="#1B1E23" stroke="#3A3F47" stroke-width="1.8"/>'
            '<polyline points="26,17 32,20 38,17" stroke="#3A3F47" stroke-width="1.4"/>'
            '<polygon points="19,27 29,29 28,33 19,32" fill="#0A0A0C" stroke="#3A3F47" stroke-width="1.2"/>'
            '<polygon points="45,27 35,29 36,33 45,32" fill="#FF2A3A" style="filter: drop-shadow(0 0 4px #FF2A3A)"/>'
            '<polygon points="23,38 41,38 44,50 20,50" fill="#111317" stroke="#3A3F47" stroke-width="1.4"/>'
            '<polygon points="28,40 36,40 32,45" fill="#C1121F"/>'
            '<path d="M24 47H28M36 47H40M32 45V50" stroke="#3A3F47" stroke-width="1.3"/>'
            '<circle cx="16.5" cy="40" r="1.3" fill="#3A3F47"/><circle cx="47.5" cy="40" r="1.3" fill="#3A3F47"/></svg>')
APP_NAME = "IRONPAW"

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&display=swap');
#MainMenu, footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}
.block-container {padding: 1.2rem 1rem 4rem;}
@media (min-width: 768px) {.block-container {padding: 2rem 3rem 4rem;}}
.card {background: #111216; border: 1px solid #3A3F47; border-radius: 18px; padding: 14px 16px; margin-bottom: 10px;}
.hero {background: linear-gradient(135deg, #C1121F2E, #C1121F0F); border: 1px solid #C1121F99; box-shadow: 0 0 20px #C1121F4D; border-radius: 22px; padding: 18px; margin-bottom: 12px;}
.big {font-size: 2.2rem; font-weight: 800; line-height: 1.1; color: #F2F4F7; text-shadow: 0 0 10px #C1121F80; font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;}
.brand {font-family: 'Orbitron', 'Eurostile', 'Bank Gothic', sans-serif; font-weight: 900; font-size: 1.15rem; letter-spacing: 0.18em; color: #F2F4F7; text-shadow: 0 0 8px #C1121F99;}
.sub {color: #A7ADB6; font-size: 0.8rem;}
.row {display: flex; justify-content: space-between; align-items: center; gap: 8px;}
.word {padding: 4px 12px; border-radius: 999px; font-weight: 800; font-size: 0.8rem; letter-spacing: 0.08em;}
.chips {display: flex; gap: 6px; overflow-x: auto; margin-bottom: 12px; padding-bottom: 2px;}
.chip {flex: 0 0 auto; background: #111216; border: 1px solid #3A3F47; border-radius: 999px; padding: 6px 12px; font-size: 0.75rem; white-space: nowrap;}
.dot {display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px;}
.stButton button {border-radius: 12px; width: 100%; min-height: 46px; font-weight: 700; border: 1px solid #3A3F47; box-shadow: 0 0 8px #C1121F33;}
.stButton button:hover {border-color: #C1121F; box-shadow: 0 0 14px #C1121F80;}
.stButton button[kind="primary"], .stButton button[data-testid="stBaseButton-primary"] {color: #FFFFFF;}
button[data-baseweb="tab"] {font-size: 0.95rem; font-weight: 700;}
button[data-baseweb="tab"][aria-selected="true"], [data-testid="stTab"][aria-selected="true"] {color: #FF4D5A; text-shadow: 0 0 8px #C1121FCC;}
div[data-baseweb="tab-highlight"] {background-color: #C1121F; box-shadow: 0 0 8px #C1121F;}
div[data-baseweb="tab-border"] {background-color: #3A3F47;}
div[data-baseweb="input"], div[data-baseweb="select"] > div {border-radius: 12px; border: 1px solid #3A3F47;}
[data-testid="stExpander"] details {border: 1px solid #3A3F47; border-radius: 12px;}
h4 {margin: 14px 0 6px;}
.lb-row {display: grid; grid-template-columns: 22px 1fr auto; gap: 10px; align-items: center; padding: 9px 8px; border-bottom: 1px solid #3A3F47;}
.lb-row:last-child {border-bottom: none;}
.lb-row.lead {background: #C1121F1F; border-radius: 10px;}
.lb-rank, .lb-val {font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;}
.lb-val {font-weight: 800; font-size: 1.05rem;}
.lb-right {text-align: right; line-height: 1.25;}
.swatch {display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 8px; vertical-align: middle;}
.kpis {display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 12px;}
.kpi {background: #111216; border: 1px solid #3A3F47; border-radius: 14px; padding: 12px 14px;}
.kpi .label {margin: 0 0 4px;}
.num {font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 1.45rem; font-weight: 800; line-height: 1.15;}
.bigv {font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 1.5rem; font-weight: 800; margin-top: 8px;}
[data-testid="stPlotlyChart"] {background: #111216; border: 1px solid #3A3F47; border-radius: 18px; padding: 10px 8px 4px; margin-bottom: 12px;}
.champ {font-size: 0.62rem; font-weight: 800; letter-spacing: 0.08em; color: #F5C542; background: #F5C5421F; border: 1px solid #F5C54266; border-radius: 999px; padding: 2px 8px; margin-left: 6px; vertical-align: middle;}
.grid {display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 12px; margin-bottom: 12px;}
.grid .card {margin: 0;}
.label {color: #A7ADB6; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.08em; margin: 12px 0 4px;}
.trade {border-top: 1px solid #3A3F47; padding-top: 6px; margin-top: 6px;}
.diary {font-style: italic; font-size: 0.85rem;}
h1, h2, h3, h4 {font-family: 'Orbitron', 'Eurostile', 'Bank Gothic', sans-serif !important; letter-spacing: 0.04em;}
.card b {font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important;}
</style>
""", unsafe_allow_html=True)

# ---------- Login ----------
if "user" not in st.session_state:
    st.markdown(f'<div class="hero"><div class="row"><div><div class="brand">{APP_NAME}</div><div class="sub">Your money, made simple.</div></div>{BEAR_SVG}</div></div>', unsafe_allow_html=True)
    pw = st.text_input("Password", type="password")
    if st.button("Log in", type="primary"):
        if pw == ADMIN_PASSWORD:
            st.session_state.user = "Admin"
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()

USER = st.session_state.user
st_autorefresh(interval=120000, key="refresh")

CELEB_URL = "https://www.bargo.ai/free-apis/congress/v1/trades?limit=40"
COLS = ["time", "type", "ticker", "entry", "shares", "dollars", "score", "stop", "target"]
POT_OF = {"day": "day", "long": "long", "crypto_day": "crypto", "crypto_long": "crypto"}
POT_NAME = {"day": "Day trading", "long": "Long term", "crypto": "Crypto"}

# ---------- Saved data (Supabase) ----------
def load_json(name, default):
    return get(OWNER, name, default)

def save_json(name, data):
    put(OWNER, name, data)

pots = load_json("pots", {"day": 0.0, "long": 0.0, "crypto": 0.0})
holdings = load_json("holdings", [])
try:
    shadow_log = get("system", "shadow_log", None)
except Exception:
    shadow_log = None
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

hold_info = []
for h in holdings:
    try:
        r = scan_long(h["ticker"])
    except Exception:
        r = None
    paid = float(h.get("paid") or 0)
    dec = decide(h["qty"], paid, r["price"], r["score"], h.get("bought")) if r else None
    if r and paid > 0:  # shadow-bot rules: SELL on a downtrend with a gain over 2%, or a loss worse than 8%
        w = "SELL" if dec["word"] == "SELL" else "BUY" if r["score"] >= 7 else "HOLD"
    else:
        w = long_word(r["score"]) if r else "HOLD"
    hold_info.append((h, r, w, dec))

# ---------- Top of screen ----------
top_l, top_r = st.columns([3, 1])
top_l.markdown(f'<div class="sub" style="padding-top:10px">{now.strftime("%a %d %b, %H:%M")}</div>', unsafe_allow_html=True)
if top_r.button("Log out"):
    del st.session_state["user"]
    st.rerun()
st.markdown(f'<div class="chips">{chips}</div>', unsafe_allow_html=True)

race_tab, home, port, celebs = st.tabs(["Race", "Home", "Portfolio", "Celebs"])

# ---------- Race ----------
MOOD_COLOR = {"Buying": GREEN, "Selling": RED, "Holding": AMBER, "Waiting": GREY, "Benched": GREY}
RACER_COLOR = {"Tyler": "#FF8A3D", "Ryan": "#F5C542", "Nathan": "#4FD1C5", "Newton": "#7AA2FF", "Morpheus": "#C084FC", "Buy and Hold": "#A7ADB6"}


def swatch(n):
    return f'<span class="swatch" style="background:{RACER_COLOR.get(n, GREY)}"></span>'


def mood(a, now_utc):
    if a.get("benched"):
        return "Benched"
    last = next((t for t in reversed(a["trades"]) if t["side"] in ("BUY", "SELL")), None)
    if last and now_utc - datetime.fromisoformat(last["time"]) < timedelta(hours=2):
        return "Buying" if last["side"] == "BUY" else "Selling"
    return "Holding" if a["positions"] else "Waiting"


def mood_pill(m):
    c = MOOD_COLOR[m]
    return f'<span class="word" style="background:{c}22; color:{c}; border:1px solid {c}66;">{m.upper()}</span>'


def champ_badge(n, champ):
    return ' <span class="champ">CHAMPION</span>' if n == champ else ""


def bot_card(n, a, champ, now_utc):
    sells = [t for t in a["trades"] if t["side"] == "SELL"]
    wins = sum(1 for t in sells if t.get("pnl", 0) > 0)
    rate = f"{wins / len(sells) * 100:.0f}% of {len(sells)}" if sells else "no closed trades"
    v = race.value(a)
    pos = "".join(f'<div class="row sub" style="margin-top:4px"><span>{x["ticker"]} x{x["shares"]:g} @ ${fp(x["entry"])}</span>'
                  f'<span>{money((x["mark"] - x["entry"]) * x["shares"])}</span></div>' for x in a["positions"]) or '<div class="sub">None.</div>'
    done = {"BUY": "Bought", "SELL": "Sold", "BENCHED": "Benched"}
    trades = "".join(f'<div class="trade"><div class="row"><b>{done.get(t["side"], t["side"])} {t["ticker"]}</b>'
                     f'<span class="sub">{datetime.fromisoformat(t["time"]).astimezone(MEL).strftime("%a %d %b %H:%M")}</span></div>'
                     f'<div class="sub">{t["reason"]}</div></div>' for t in reversed(a["trades"][-3:])) or '<div class="sub">No trades yet.</div>'
    di = a.get("diary") or {}
    diary = (f'<div class="diary">{di["text"]}</div>' if di.get("day") == now_utc.astimezone(MEL).date().isoformat()
             else '<div class="sub">No diary entry yet today.</div>')
    return (f'<div class="card" style="border-top: 3px solid {RACER_COLOR.get(n, GREY)}"><div class="row"><b style="font-size:1.1rem">{swatch(n)}{n}{champ_badge(n, champ)}</b>'
            f'{mood_pill(mood(a, now_utc))}</div><div class="sub" style="margin-top:4px">{STYLES.get(n, "")}</div>'
            f'<div class="bigv">${v:,.0f}</div><div>{money(v - race.START_CASH)} <span class="sub">({(v / race.START_CASH - 1) * 100:+.1f}% this season)</span></div>'
            + line("Open positions", str(len(a["positions"])))
            + line("Win rate", rate) + f'<div class="label">Positions</div>{pos}<div class="label">Last 3 trades</div>{trades}'
            + f'<div class="label">Today&#39;s diary</div>{diary}</div>')


with race_tab:
    race_pick = st.radio("Race", ["STOCKS", "CRYPTO"], horizontal=True, label_visibility="collapsed", key="race_pick")
    rc = next(r for r in race.ALL_RACES.values() if r["name"] == race_pick)
    now_utc = datetime.now(timezone.utc)
    rdoc = None
    if rc["key"] not in race.ENABLED:
        st.markdown('<div class="card sub">The crypto race is switched off for now: only the ASX race is running.</div>', unsafe_allow_html=True)
    else:
        try:
            rdoc = get("system", rc["doc"], None)
        except Exception:
            rdoc = None
        if not rdoc:
            st.markdown('<div class="card sub">The race starts on the next bot run.</div>', unsafe_allow_html=True)
    if rdoc:
        table = race.standings(rdoc)
        champ = rdoc.get("champion")
        st.markdown(f'<div class="sub" style="margin-bottom:6px">Season {rdoc["season"]} · {race.days_left(rdoc, now_utc)} days left · '
                    f'paper money only, no real orders</div>', unsafe_allow_html=True)
        accts = rdoc["accounts"]
        lead_n, lead_v = table[0]
        bench_v = race.value(accts[race.BENCH])
        n_trades = sum(1 for n in race.BOTS for t in accts[n]["trades"] if t["side"] in ("BUY", "SELL"))
        beat = sum(1 for n in race.BOTS if race.value(accts[n]) > bench_v)
        kpis = [("Leader", f"{swatch(lead_n)}{lead_n}", f"{(lead_v / race.START_CASH - 1) * 100:+.1f}%"),
                ("Days left", str(race.days_left(rdoc, now_utc)), f"of {race.SEASON_DAYS}, season {rdoc['season']}"),
                ("Bot trades", str(n_trades), "this season"),
                ("Beating Buy and Hold", f"{beat} of {len(race.BOTS)}", f"benchmark {(bench_v / race.START_CASH - 1) * 100:+.1f}%")]
        st.markdown('<div class="kpis">' + "".join(f'<div class="kpi"><div class="label">{k}</div><div class="num">{v}</div><div class="sub">{s}</div></div>'
                                                   for k, v, s in kpis) + '</div>', unsafe_allow_html=True)
        rows = "".join(f'<div class="lb-row{" lead" if i == 1 else ""}"><span class="lb-rank">{i}</span><span>{swatch(n)}{n}{champ_badge(n, champ)}</span>'
                       f'<span class="lb-right"><span class="lb-val">${v:,.0f}</span><br>{money(v - race.START_CASH)} '
                       f'<span class="sub">({(v / race.START_CASH - 1) * 100:+.1f}%)</span></span></div>' for i, (n, v) in enumerate(table, 1))
        st.markdown(f'<div class="card">{rows}</div>', unsafe_allow_html=True)
        hist = rdoc.get("history", [])
        xs = [pd.Timestamp(h["t"]).tz_convert(MEL) for h in hist]
        fig = go.Figure()
        for n, _ in table:
            fig.add_trace(go.Scatter(x=xs, y=[h["v"].get(n) for h in hist], mode="lines", name=n,
                                     line=dict(width=1.6, color=RACER_COLOR.get(n), dash="dot" if n == race.BENCH else "solid"),
                                     hovertemplate="%{y:$,.0f}"))
        grid_line = dict(gridcolor="rgba(58,63,71,0.45)", zeroline=False, showline=False, tickfont=dict(size=11))
        fig.update_layout(height=340, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#A7ADB6", size=11), hovermode="x unified", hoverlabel=dict(bgcolor="#111216", bordercolor="#3A3F47"),
                          legend=dict(orientation="h", y=-0.18, font=dict(size=11)), xaxis=grid_line, yaxis=dict(tickprefix="$", **grid_line))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.markdown('<div class="grid">' + "".join(bot_card(n, rdoc["accounts"][n], champ, now_utc) for n, _ in table) + '</div>', unsafe_allow_html=True)
    st.markdown("#### Hall of Fame")
    try:
        hof = get("system", "hall_of_fame", None) or []
    except Exception:
        hof = []
    past = [e for e in hof if e.get("race") == rc["key"]]
    if not past:
        ends = f" Season {rdoc['season']} ends {race.season_end(rdoc).astimezone(MEL).strftime('%a %d %b')}." if rdoc else ""
        st.markdown(f'<div class="card sub">No finished seasons yet.{ends}</div>', unsafe_allow_html=True)
    for e in reversed(past):
        win = next(x for x in e["standings"] if x["name"] == e["winner"])
        bench = next((x for x in e["standings"] if x["name"] == race.BENCH), None)
        when = f'{datetime.fromisoformat(e["start"]).astimezone(MEL).strftime("%d %b")} to {datetime.fromisoformat(e["end"]).astimezone(MEL).strftime("%d %b %Y")}'
        st.markdown(f'<div class="card"><div class="row"><b style="font-size:1.1rem">Season {e["season"]}</b><span class="champ">{e["winner"].upper()}</span></div>'
                    + line("Winner", f'{e["winner"]} {money(win["value"] - race.START_CASH)} ({win["pct"]:+.1f}%)')
                    + (line("Buy and Hold", f'{bench["pct"]:+.1f}%') if bench else "") + line("Dates", when) + '</div>', unsafe_allow_html=True)
    try:
        rset = get("system", "race_settings", None) or {}
    except Exception:
        rset = None
    modes = {"trade": "Pings: every trade", "summary": "Pings: daily summary"}
    if rset is not None:
        cur = rset.get("pings", "trade")
        pings = st.radio("Notifications", list(modes), index=list(modes).index(cur), format_func=modes.get, horizontal=True, key="pings")
        if pings != cur:
            try:
                put("system", "race_settings", {**rset, "pings": pings})
                st.success(f"Saved: {modes[pings]}. Season results are always sent.")
            except Exception:
                st.error("Could not save the setting. Try again.")

# ---------- Home ----------
with home:
    total = sum(pots.values())
    st.markdown(f'<div class="hero"><div class="row"><div><div class="brand">{APP_NAME}</div><div class="sub">Hi {USER}</div></div>{BEAR_SVG}</div><div class="big" style="margin-top:6px">${total:,.0f}</div>'
                f'<div class="sub">in your pots</div><div style="margin-top:10px">Today {money(total_pl)} '
                f'<span class="sub">&nbsp;{ups} up · {downs} down</span></div></div>', unsafe_allow_html=True)
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
        new_paid = st.number_input("What you paid per share ($)", min_value=0.0, value=0.0)
        new_when = st.date_input("Bought on", value=datetime.now(MEL).date())
        if st.button("Add it", type="primary") and new_t.strip() and new_q > 0:
            tk = new_t.strip().upper()
            if "." not in tk and "-" not in tk:
                tk += ".AX"
            item = {"ticker": tk, "qty": new_q, "bought": new_when.isoformat()}
            if new_paid > 0:
                item["paid"] = new_paid
            holdings.append(item)
            save_json("holdings", holdings)
            st.rerun()
    if not holdings:
        st.markdown('<div class="card sub">Nothing added yet.</div>', unsafe_allow_html=True)
    plain = {"BUY": "Looking strong. Fine to buy more.", "HOLD": "Keep it.", "SELL": "Trending down. Think about selling."}
    sold_keys = {s["key"]: s for s in (shadow_log or {}).get("sales", [])}
    for i, (h, r, w, dec) in enumerate(hold_info):
        if r and float(h.get("paid") or 0) > 0:
            body = (line("Paid", f"${fp(float(h['paid']))}") + line("Now", f"${fp(r['price'])}") + line("Worth", f"${r['price'] * h['qty']:,.0f}")
                    + line("Gain / loss", f'{money(dec["gain"])} <span class="sub">({dec["pct"]:+.1f}%)</span>'))
            body += f'<div class="sub" style="margin-top:8px">{dec["reason"]}</div>'
            done = sold_keys.get(holding_key(h))
            if done:
                body += f'<div class="sub" style="margin-top:6px">The shadow bot already paper-sold this on {done["date"]}.</div>'
        elif r:
            body = line("Price", f"${fp(r['price'])}") + line("Worth", f"${r['price'] * h['qty']:,.0f}")
            body += f'<div class="sub" style="margin-top:8px">{plain[w]} ({r["why"]})</div>'
            body += '<div class="sub" style="margin-top:6px">No price paid saved for this one, so the shadow bot leaves it alone.</div>'
        else:
            body = '<div class="sub" style="margin-top:6px">No data. Check the code.</div>'
        card(f'{h["ticker"]} <span class="sub">x{h["qty"]:g}</span>', w, body)
    st.markdown("#### Bought today")
    if len(pnl) == 0:
        st.markdown('<div class="card sub">Nothing bought today.</div>', unsafe_allow_html=True)
    for _, r in pnl.iterrows():
        w, why = trade_word(r, asx_closing)
        body = line("Paid", f"${fp(float(r['entry']))}") + line("Now", f"${fp(float(r['now']))}") + line("Gain / loss", money(r["gl"]))
        card(r["ticker"], w, body + f'<div class="sub" style="margin-top:8px">{why}</div>')
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

    # ---------- Shadow bot ----------
    st.markdown("#### Shadow bot")
    st.markdown('<div class="sub">Pretend money only. It shadows your holdings, never touches the real ones and never places orders.</div>', unsafe_allow_html=True)
    sh_sales, sh_buys = (shadow_log or {}).get("sales", []), (shadow_log or {}).get("buys", [])
    if not sh_sales and not sh_buys:
        st.markdown('<div class="card sub">No shadow moves yet. It sells when a holding turns down with a gain over 2%, or loses more than 8%.</div>', unsafe_allow_html=True)
    else:
        def px_now(tk, fallback):
            return live_price(tk) or fallback
        sale_pl = sum(s["gain"] for s in sh_sales)
        buy_pl = sum(b["shares"] * px_now(b["ticker"], b.get("mark", b["price"])) - b["cost"] for b in sh_buys)
        brokerage = sum(s.get("costs", 10.0) for s in sh_sales) + sum(b.get("brokerage", 10.0) for b in sh_buys)
        sh_boxes = (f'<div class="card" style="flex:1; margin:0"><div class="sub">Total paper profit or loss</div>{money(sale_pl + buy_pl)}</div>'
                    f'<div class="card" style="flex:1; margin:0"><div class="sub">Brokerage paid</div><b>${brokerage:,.0f}</b></div>'
                    f'<div class="card" style="flex:1; margin:0"><div class="sub">Moves</div><b>{len(sh_sales)} sold, {len(sh_buys)} bought</b></div>')
        st.markdown(f'<div class="row" style="align-items:stretch">{sh_boxes}</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub" style="margin:6px 0 10px">Sales count the profit made at the sale. Buys count how they are doing now, after costs.</div>', unsafe_allow_html=True)
        waiting = sum(s["proceeds"] for s in sh_sales if not s.get("reinvested"))
        if waiting > 0:
            st.markdown(f'<div class="card sub">Paper cash waiting: ${waiting:,.2f}. No Long term idea scores BUY right now.</div>', unsafe_allow_html=True)
        sold_name = {s["key"]: s["ticker"] for s in sh_sales}
        for s in reversed(sh_sales):
            now_p = px_now(s["ticker"], s["price"])
            since = (now_p - s["price"]) / s["price"] * 100
            body = (line("Sold", f"${fp(s['price'])} x{s['qty']:g}") + line("Date", s["date"])
                    + line("Gain / loss at the sale", f'{money(s["gain"])} <span class="sub">({s["pct"]:+.1f}%)</span>')
                    + line("Price now", f'${fp(now_p)} <span class="sub">({since:+.1f}% since the sale)</span>')
                    + f'<div class="sub" style="margin-top:8px">{s["reason"]}</div>')
            card(s["ticker"], "SELL", body)
        for b in reversed(sh_buys):
            now_p = px_now(b["ticker"], b.get("mark", b["price"]))
            pl = b["shares"] * now_p - b["cost"]
            body = (line("Bought", f"${fp(b['price'])} x{b['shares']:g}") + line("Date", b["date"]) + line("Now", f"${fp(now_p)}")
                    + line("Gain / loss since", f'{money(pl)} <span class="sub">({pl / b["cost"] * 100:+.1f}%)</span>')
                    + f'<div class="sub" style="margin-top:8px">Best Long term idea (score {b["score"]}), bought with the proceeds from selling {sold_name.get(b["sale_key"], "a holding")}.</div>')
            card(b["ticker"], "BUY", body)

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

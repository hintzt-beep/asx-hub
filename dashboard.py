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
.block-container {padding: 0.8rem 0.8rem 3rem;}
@media (min-width: 768px) {.block-container {padding: 1.4rem 2.5rem 3rem;}}
.card {background: #111216; border: 1px solid #3A3F47; border-radius: 14px; padding: 10px 14px; margin-bottom: 8px;}
.hero {background: linear-gradient(135deg, #C1121F2E, #C1121F0F); border: 1px solid #C1121F99; box-shadow: 0 0 20px #C1121F4D; border-radius: 16px; padding: 14px 16px; margin-bottom: 10px;}
.big {font-size: 2.2rem; font-weight: 800; line-height: 1.1; color: #F2F4F7; text-shadow: 0 0 10px #C1121F80; font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;}
.brand {font-family: 'Orbitron', 'Eurostile', 'Bank Gothic', sans-serif; font-weight: 900; font-size: 1.15rem; letter-spacing: 0.18em; color: #F2F4F7; text-shadow: 0 0 8px #C1121F99;}
.sub {color: #A7ADB6; font-size: 0.8rem;}
.row {display: flex; justify-content: space-between; align-items: center; gap: 8px;}
.word {padding: 4px 12px; border-radius: 999px; font-weight: 800; font-size: 0.8rem; letter-spacing: 0.08em;}
.chips {display: flex; gap: 6px; overflow-x: auto; margin-bottom: 8px; padding-bottom: 2px;}
.chip {flex: 0 0 auto; background: #111216; border: 1px solid #3A3F47; border-radius: 999px; padding: 4px 10px; font-size: 0.72rem; white-space: nowrap;}
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
h4 {margin: 10px 0 4px; font-size: 1rem;}
.lb-row {display: grid; grid-template-columns: 22px 1fr auto; gap: 10px; align-items: center; padding: 9px 8px; border-bottom: 1px solid #3A3F47;}
.lb-row:last-child {border-bottom: none;}
.lb-row.lead {background: #C1121F1F; border-radius: 10px;}
.lb-rank, .lb-val {font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;}
.lb-val {font-weight: 800; font-size: 1.05rem;}
.lb-right {text-align: right; line-height: 1.25;}
.swatch {display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 8px; vertical-align: middle;}
.kpis {display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; margin-bottom: 8px;}
.kpi {background: #111216; border: 1px solid #3A3F47; border-radius: 12px; padding: 8px 12px;}
.kpi .label {margin: 0 0 4px;}
.num {font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 1.2rem; font-weight: 800; line-height: 1.15;}
.bigv {font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 1.5rem; font-weight: 800; margin-top: 8px;}
[data-testid="stPlotlyChart"] {background: #111216; border: 1px solid #3A3F47; border-radius: 18px; padding: 10px 8px 4px; margin-bottom: 12px;}
.champ {font-size: 0.62rem; font-weight: 800; letter-spacing: 0.08em; color: #F5C542; background: #F5C5421F; border: 1px solid #F5C54266; border-radius: 999px; padding: 2px 8px; margin-left: 6px; vertical-align: middle;}
.grid {display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 8px; margin-bottom: 8px; align-items: start;}
.grid .card {margin: 0;}
.label {color: #A7ADB6; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.08em; margin: 12px 0 4px;}
.trade {border-top: 1px solid #3A3F47; padding-top: 6px; margin-top: 6px;}
.diary {font-style: italic; font-size: 0.85rem;}
.mini {display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 0.85rem; padding: 0.35rem 0; border-bottom: 1px solid #3A3F47;}
.mini:last-child {border-bottom: none;}
.mini .word {font-size: 0.6rem; padding: 2px 7px;}
h1, h2, h3, h4 {font-family: 'Orbitron', 'Eurostile', 'Bank Gothic', sans-serif !important; letter-spacing: 0.04em;}
details.more > summary {list-style: none; cursor: pointer;}
details.more > summary::-webkit-details-marker {display: none;}
details.more > summary .tap {color: #A7ADB6; font-size: 0.7rem;}
details.more > summary .tap::after {content: "▾ details";}
details.more[open] > summary .tap::after {content: "▴ less";}
.st-key-topbar [data-testid="stHorizontalBlock"] {flex-wrap: nowrap; gap: 8px;}
.st-key-topbar [data-testid="stColumn"] {min-width: 0 !important; width: auto !important;}
.st-key-topbar [data-testid="stColumn"]:last-child {flex: 0 0 auto !important;}
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
chips, asx_open, asx_closing, mkts = "", False, False, []
for name, tz, oh, om, ch, cm in [("ASX", "Australia/Sydney", 10, 0, 16, 0),
                                 ("TSX", "America/Toronto", 9, 30, 16, 0),
                                 ("NYSE", "America/New_York", 9, 30, 16, 0)]:
    is_open, left = market_status(tz, oh, om, ch, cm)
    if name == "ASX":
        asx_open, asx_closing = is_open, is_open and left < 900
    local = datetime.now(ZoneInfo(tz)).strftime("%H:%M")
    word = "closes" if is_open else "opens"
    mkts.append((name, is_open, left))
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

# ---------- Top of screen ----------
prefs = load_json("prefs", {})
if "desktop_view" not in st.session_state:
    st.session_state.desktop_view = bool(prefs.get("desktop", False))
desktop = st.session_state.desktop_view


def save_desktop():
    save_json("prefs", {**prefs, "desktop": st.session_state.desktop_view})


def settings_menu(where):
    """Desktop view, notifications and log out, tucked into one small menu."""
    with where.popover("Settings"):
        st.toggle("Desktop view", key="desktop_view", on_change=save_desktop)
        try:
            rset = get("system", "race_settings", None) or {}
        except Exception:
            rset = None
        if rset is not None:
            modes = {"trade": "Every trade", "summary": "Daily summary"}
            cur = rset.get("pings", "summary")
            pings = st.radio("Phone pings", list(modes), index=list(modes).index(cur), format_func=modes.get, key="pings")
            if pings != cur:
                try:
                    put("system", "race_settings", {**rset, "pings": pings})
                    st.success("Saved. Coach picks and scorecards are always sent.")
                except Exception:
                    st.error("Could not save the setting. Try again.")
        if st.button("Log out"):
            del st.session_state["user"]
            st.rerun()


if not desktop:  # phone view: tabs
    top_l, top_r = st.container(key="topbar").columns([3, 1.2], vertical_alignment="center")
    top_l.markdown(f'<div class="row" style="justify-content:flex-start; gap:10px">{BEAR_SVG}<div><div class="brand">{APP_NAME}</div>'
                   f'<div class="sub">{now.strftime("%a %d %b, %H:%M")}</div></div></div>', unsafe_allow_html=True)
    settings_menu(top_r)
    st.markdown(f'<div class="chips">{chips}</div>', unsafe_allow_html=True)
    home, race_tab, bt_tab, sugg, port, insiders = st.tabs(["Home", "Race", "Backtest", "Suggestions", "Portfolio", "Insiders"])

# ---------- Race ----------
MOOD_COLOR = {"Buying": GREEN, "Selling": RED, "Holding": AMBER, "Waiting": GREY, "Benched": GREY}
RACER_COLOR = {"Tyler": "#FF8A3D", "Ryan": "#F5C542", "Nathan": "#4FD1C5", "Newton": "#7AA2FF", "Morpheus": "#C084FC",
               "Coach's Picks": "#F472B6", "Buy and Hold": "#A7ADB6"}


def n_trades(a):
    return sum(1 for t in a.get("trades", []) if t.get("side") in ("BUY", "SELL"))


def lb_row(i, n, a, champ, compact=False):
    """Leaderboard row: time-weighted % first, then value, money put in, fees and trades (one line when compact)."""
    r = race.twr(a)
    pct = f'<span class="lb-val" style="color:{GREEN if r > 0 else RED if r < 0 else "inherit"}">{r:+.2f}%</span>'
    if compact:
        return (f'<div class="lb-row{" lead" if i == 1 else ""}"><span class="lb-rank">{i}</span><span>{swatch(n)}{n}{champ_badge(n, champ)}</span>'
                f'<span class="lb-right">{pct} <span class="sub">${race.value(a):,.0f} · {race.trades_word(a)}</span></span></div>')
    return (f'<div class="lb-row{" lead" if i == 1 else ""}"><span class="lb-rank">{i}</span><span>{swatch(n)}{n}{champ_badge(n, champ)}</span>'
            f'<span class="lb-right">{pct}<br>'
            f'<span class="sub">${race.value(a):,.0f} · {race.trades_word(a)}</span></span></div>')


def risk_log_html(rdoc, n=10, wrap=True):
    """The last n risk-manager decisions, newest first."""
    rows = ""
    for e in reversed(rdoc.get("risk_log", [])[-n:]):
        ok = e["decision"] == "approve"
        c = GREEN if ok else RED
        rows += (f'<div class="mini"><span><span class="word" style="background:{c}22; color:{c}; border:1px solid {c}66;">'
                 f'{"APPROVED" if ok else "BLOCKED"}</span> <b>{e["bot"]}</b> {e["ticker"]} ${e["cost"]:,.2f}'
                 f'<br><span class="sub">{e["reason"]}</span></span><span class="sub">{datetime.fromisoformat(e["time"]).astimezone(MEL).strftime("%a %H:%M")}</span></div>')
    return (f'<div class="card">{rows}</div>' if wrap else rows) if rows else ""


def race_error_card(e):
    print("Race section failed:", repr(e))
    return ('<div class="card"><b>The Race section couldn&#39;t load right now.</b><div class="sub" style="margin-top:4px">'
            f'{type(e).__name__}. The rest of the app still works and the bots keep running. Try again in a few minutes.</div></div>')


def load_system(name, default):
    try:
        return get("system", name, None) or default
    except Exception:
        return default


def hof_view(e):
    """Hall of Fame entry: new 3-week scorecards, or an old season entry."""
    rows = e.get("results") or e.get("standings") or []
    win = next((x for x in rows if x["name"] == e["winner"]), {"pct": 0.0})
    bench = next((x for x in rows if x["name"] == race.BENCH), None)
    label = f'Scorecard {e["scorecard"]}' if "scorecard" in e else f'Season {e.get("season")}'
    return label, win["pct"], bench["pct"] if bench else None


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
    r = race.twr(a)
    held = ", ".join(x["ticker"].replace(".AX", "").replace("-AUD", "") for x in a["positions"]) or "cash"
    return (f'<details class="card more" style="border-top: 3px solid {RACER_COLOR.get(n, GREY)}"><summary>'
            f'<div class="row"><b style="font-size:1.05rem">{swatch(n)}{n}{champ_badge(n, champ)}</b>{mood_pill(mood(a, now_utc))}</div>'
            f'<div class="row" style="margin-top:4px"><span class="bigv" style="margin:0; color:{GREEN if r > 0 else RED if r < 0 else "inherit"}">{r:+.2f}%</span>'
            f'<span class="sub" style="text-align:right">${v:,.0f} · holding {held}<br><span class="tap"></span></span></div></summary>'
            f'<div class="sub" style="margin-top:6px">{STYLES.get(n, "")}</div>'
            + line("Put in", f'${a.get("contributed", 0):,.0f}') + line("Fees paid", f'${a.get("fees_paid", 0):,.2f}') + line("Win rate", rate)
            + f'<div class="label">Positions</div>{pos}<div class="label">Last 3 trades</div>{trades}'
            + f'<div class="label">Today&#39;s diary</div>{diary}</details>')


# ---------- Desktop view: the whole dashboard on one screen, no page scrolling ----------
DESK_CSS = """<style>
html {font-size: clamp(12px, 0.55vw + 5px, 15px);}
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] {display: none !important;}
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {overflow: hidden !important;}
.block-container {padding: 0.45rem 0.9rem 0 !important; max-width: 100% !important;}
[data-testid="stVerticalBlock"] {gap: 0.45rem;}
[data-testid="stHorizontalBlock"] {gap: 0.6rem;}
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style) {display: none;}
[data-testid="stElementContainer"]:has(iframe) {position: absolute; height: 0; overflow: hidden;}
:root {--top: 2.7rem; --bot: 24vh; --mid: calc(100vh - var(--top) - var(--bot) - 2.1rem);}
.pn {background: #111216; border: 1px solid #3A3F47; border-radius: 12px; padding: 0.5rem 0.7rem; margin-bottom: 0.7rem; overflow-y: auto; scrollbar-width: thin; scrollbar-color: #3A3F47 transparent;}
.pn-h {display: flex; justify-content: space-between; gap: 8px; color: #A7ADB6; font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.35rem;}
.h-mid {height: var(--mid);} .h-bot {height: var(--bot);}
.h-lb {height: calc(var(--mid) - 35vh - 0.45rem);}
.h-home {height: calc(var(--mid) * 0.4 - 0.25rem);} .h-risk {height: calc(var(--mid) * 0.32 - 0.7rem);} .h-hof {height: calc(var(--mid) * 0.28 - 0.7rem);}
.tb {display: flex; align-items: center; gap: 0.7rem; white-space: nowrap; overflow: hidden;}
.tb svg {width: 30px; height: 30px; flex: none;}
.tb .brand {font-size: 0.95rem;}
.mchip {font-size: 0.68rem; border: 1px solid #3A3F47; border-radius: 999px; padding: 1px 7px;}
.tb-total {font-family: MONO; font-weight: 800; font-size: 1.1rem; white-space: nowrap;}
.pn .lb-row {padding: 0.3rem 0.45rem;} .pn .lb-val {font-size: 0.92rem;}
.pn .big {font-size: 1.7rem;}
.mini {display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 0.78rem; padding: 0.28rem 0; border-bottom: 1px solid #3A3F47;}
.mini:last-child {border-bottom: none;}
.pn .mini .sub {display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden;}
.bcs {display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 11rem), 1fr)); gap: 0.45rem;}
.bc {background: #0E0F12; border: 1px solid #3A3F47; border-radius: 10px; padding: 0.4rem 0.55rem;}
.bc .v {font-family: MONO; font-weight: 800; font-size: 1.02rem; margin-top: 2px;}
.bc .word, .mini .word {font-size: 0.56rem; padding: 2px 6px;}
.bc .lt {font-size: 0.7rem; color: #A7ADB6; margin-top: 3px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;}
.stRadio label, .stToggle label {font-size: 0.8rem;}
.stButton button {min-height: 2rem; padding: 0 0.8rem;}
[data-testid="stPlotlyChart"] {height: 35vh; padding: 4px 4px 0; margin: 0;}
[data-testid="stElementContainer"]:has([data-testid="stPlotlyChart"]), [data-testid="stFullScreenFrame"]:has([data-testid="stPlotlyChart"]) {height: 35vh !important; min-height: 0 !important; flex: 0 0 35vh !important; overflow: hidden;}
[data-testid="stPlotlyChart"] > div, [data-testid="stPlotlyChart"] .js-plotly-plot, [data-testid="stPlotlyChart"] .plot-container {height: 100% !important;}
</style>""".replace("MONO", "'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace")


def pn(title, body, cls, right=""):
    return f'<div class="pn {cls}"><div class="pn-h"><span>{title}</span><span>{right}</span></div>{body}</div>'


def mini(left, right):
    return f'<div class="mini"><span>{left}</span><span style="text-align:right">{right}</span></div>'


def bot_mini(n, a, now_utc):
    v = race.value(a)
    last = a["trades"][-1] if a["trades"] else None
    done = {"BUY": "Bought", "SELL": "Sold", "BENCHED": "Benched"}
    lt = (f'<b>{done.get(last["side"], last["side"])} {last["ticker"]}</b> · {datetime.fromisoformat(last["time"]).astimezone(MEL).strftime("%a %H:%M")}: {last["reason"]}'
          if last else "No trades yet.")
    return (f'<div class="bc" style="border-top: 3px solid {RACER_COLOR.get(n, GREY)}"><div class="row"><b>{swatch(n)}{n}</b>{mood_pill(mood(a, now_utc))}</div>'
            f'<div class="v">{race.twr(a):+.2f}% <span class="sub">${v:,.0f}</span></div><div class="lt">{lt}</div></div>')


def render_desktop():
    st.markdown(DESK_CSS, unsafe_allow_html=True)
    now_utc = datetime.now(timezone.utc)
    total = sum(pots.values())
    mchips = "".join(f'<span class="mchip"><span class="dot" style="background:{GREEN if o else GREY}"></span>{n} {"open" if o else "opens " + fmt_left(left)}</span>'
                     for n, o, left in mkts) + f'<span class="mchip"><span class="dot" style="background:{GREEN}"></span>Crypto open</span>'
    c_brand, c_race, c_set = st.columns([7.2, 1.7, 1.1], vertical_alignment="center")
    c_brand.markdown(f'<div class="tb">{BEAR_SVG}<span class="brand">{APP_NAME}</span><span class="sub">{now.strftime("%a %d %b, %H:%M")}</span>{mchips}</div>', unsafe_allow_html=True)
    pick_race = c_race.radio("Race", ["STOCKS", "CRYPTO"], horizontal=True, label_visibility="collapsed", key="race_pick")
    settings_menu(c_set)

    rc = next(r for r in race.ALL_RACES.values() if r["name"] == pick_race)
    rdoc = None
    if rc["key"] in race.ENABLED:
        try:
            rdoc = race.load_race(rc, create=False)  # repairs and saves any account left over from older rules
            rdoc = race.with_defaults(rdoc) if rdoc else None
        except Exception:
            rdoc = None
    left, centre, right = st.columns([1.05, 1.6, 1.55])

    # left: Home summary, Hall of Fame, pings
    pots_html = "".join(mini(f'{POT_NAME[k]}<br><span class="sub">${cash[k]:,.0f} free</span>', f"<b>${pots[k]:,.0f}</b>") for k in pots)
    left.markdown(pn("Home", f'<div class="sub">Hi {USER}</div><div class="big">${total:,.0f}</div>'
                     f'<div style="margin:2px 0 6px">Today {money(total_pl)} <span class="sub">{ups} up · {downs} down</span></div>{pots_html}', "h-home"), unsafe_allow_html=True)
    try:
        hof = [e for e in (get("system", "hall_of_fame", None) or []) if e.get("race") == rc["key"]]
    except Exception:
        hof = []
    hof_html = "".join(mini(f'{hof_view(e)[0]}<br><span class="sub">{datetime.fromisoformat(e["end"]).astimezone(MEL).strftime("%d %b %Y")}</span>',
                            f'{swatch(e["winner"])}<b>{e["winner"]}</b> {hof_view(e)[1]:+.1f}%') for e in reversed(hof))
    ends = f' Scorecard {rdoc["scorecard"]} lands {race.scorecard_end(rdoc).astimezone(MEL).strftime("%a %d %b")}.' if rdoc else ""
    left.markdown(pn("Risk manager", (risk_log_html(rdoc, wrap=False) if rdoc else "") or '<div class="sub">No decisions yet.</div>', "h-risk", "last 10"),
                  unsafe_allow_html=True)
    left.markdown(pn("Hall of Fame", hof_html or f'<div class="sub">No scorecards yet.{ends}</div>', "h-hof", rc["name"]), unsafe_allow_html=True)

    # centre: leaderboard, then the chart; right: racer cards
    if not rdoc:
        msg = "The crypto race is switched off." if rc["key"] not in race.ENABLED else "The race starts on the next bot run."
        centre.markdown(pn(f'{rc["name"]} race', f'<div class="sub">{msg}</div>', "h-mid"), unsafe_allow_html=True)
        right.markdown(pn("Racers", '<div class="sub">No racers yet.</div>', "h-mid"), unsafe_allow_html=True)
    else:
        table, champ = race.standings(rdoc), rdoc.get("champion")
        rows = "".join(lb_row(i, n, rdoc["accounts"][n], champ, compact=True) for i, (n, _) in enumerate(table, 1))
        centre.markdown(pn(f'{rc["name"]} leaderboard', rows, "h-lb", f'ranked by time-weighted return · scorecard in {race.days_left(rdoc, now_utc)} days'), unsafe_allow_html=True)
        hist = rdoc.get("history", [])
        xs = [pd.Timestamp(h["t"]).tz_convert(MEL) for h in hist]
        fig = go.Figure()
        for n, _ in table:
            fig.add_trace(go.Scatter(x=xs, y=[h["v"].get(n) for h in hist], mode="lines", name=n, hovertemplate="%{y:$,.0f}",
                                     line=dict(width=1.5, color=RACER_COLOR.get(n), dash="dot" if n == race.BENCH else "solid")))
        grid_line = dict(gridcolor="rgba(58,63,71,0.45)", zeroline=False, showline=False, tickfont=dict(size=10))
        fig.update_layout(autosize=True, margin=dict(l=4, r=4, t=4, b=4), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#A7ADB6", size=10), hovermode="x unified", hoverlabel=dict(bgcolor="#111216", bordercolor="#3A3F47"),
                          showlegend=False, xaxis=grid_line, yaxis=dict(tickprefix="$", **grid_line))  # leaderboard colours are the legend
        centre.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "responsive": True})
        right.markdown(pn("Racers", '<div class="bcs">' + "".join(bot_mini(n, rdoc["accounts"][n], now_utc) for n, _ in table) + "</div>", "h-mid",
                          "mood · value · last trade"), unsafe_allow_html=True)

    # bottom strip: Portfolio and Insiders
    bot_s, bot_l, bot_r = st.columns(3)
    reports, picks = load_system("coach_reports", []), load_system("coach_picks", [])
    if reports:
        rp = reports[-1]
        s_html = (f'<div style="font-size:0.8rem">{rp["summary"]}</div>'
                  + "".join(mini(f'{swatch(s["bot"])}<b>{s["bot"]}</b> <span class="sub">{s["race"]}: {s["change"]}</span>',
                                 f'<span class="sub">{s.get("status", "new")}</span>') for s in rp.get("suggestions", [])))
    else:
        s_html = '<div class="sub">No Coach reports yet.</div>'
    if picks:
        for key, res in picks[-1].get("races", {}).items():
            rcx = race.ALL_RACES[key]
            s_html += "".join(mini(f'{pill("BUY")} <b>{o["ticker"]}</b> <span class="sub">Coach\'s pick, stop ${o["stop"]:,.2f}</span>', f'${o["dollars"]:,.0f}')
                              for o in res.get("picks", [])) or mini(f'<span class="sub">{rcx["name"]}: no Coach\'s Picks this week</span>', "")
    bot_s.markdown(pn("Suggestions", s_html, "h-bot", "approve on the phone view"), unsafe_allow_html=True)
    bought = "".join(mini(f'<b>{r["ticker"]}</b> <span class="sub">paid ${fp(float(r["entry"]))}, now ${fp(float(r["now"]))}</span>', money(r["gl"]))
                     for _, r in pnl.iterrows()) or '<div class="sub">Nothing bought today.</div>'
    sh_sales, sh_buys = (shadow_log or {}).get("sales", []), (shadow_log or {}).get("buys", [])
    sh_pl = sum(s["gain"] for s in sh_sales) + sum(b["shares"] * (live_price(b["ticker"]) or b.get("mark", b["price"])) - b["cost"] for b in sh_buys)
    sh_brk = sum(s.get("costs", 10.0) for s in sh_sales) + sum(b.get("brokerage", 10.0) for b in sh_buys)
    moves = sorted([(s["date"], "SELL", s["ticker"], s["reason"]) for s in sh_sales] + [(b["date"], "BUY", b["ticker"], f'Best Long term idea, score {b["score"]}.') for b in sh_buys], reverse=True)
    moves_html = "".join(mini(f'{pill(w)} <b>{tk}</b> <span class="sub">{why}</span>', f'<span class="sub">{when}</span>') for when, w, tk, why in moves)
    bot_l.markdown(pn("Portfolio", f'<div class="label" style="margin-top:0">Bought today</div>{bought}<div class="label">Shadow bot (paper)</div>'
                      + mini("Total paper profit or loss", money(sh_pl)) + mini("Brokerage paid", f"${sh_brk:,.0f}")
                      + (moves_html or '<div class="sub">No shadow moves yet.</div>'), "h-bot"), unsafe_allow_html=True)
    try:
        ins = [t for t in celeb_trades()[:40] if isinstance(t, dict)]
        ins_err = ""
    except Exception as e:
        ins, ins_err = [], f"Couldn't load right now: {e}"
    ins_rows = ""
    for t in ins:
        kind_txt = str(pick(t, "type", "transaction_type", "transaction", "side")).lower()
        w = "BUY" if ("purchase" in kind_txt or "buy" in kind_txt) else "SELL" if ("sale" in kind_txt or "sell" in kind_txt) else "HOLD"
        ins_rows += mini(f'{pill(w)} <b>{pick(t, "ticker", "symbol") or "?"}</b> <span class="sub">{pick(t, "member", "member_name", "name", "politician", "representative", "senator")}</span>',
                         f'<span class="sub">{pick(t, "amount", "amount_range", "range")} · {pick(t, "transaction_date", "traded", "trade_date", "date")}</span>')
    bot_r.markdown(pn("Insiders", ins_rows or f'<div class="sub">{ins_err or "No trades to show."}</div>', "h-bot", "US politicians' trades, Bargo"), unsafe_allow_html=True)


if desktop:
    try:
        render_desktop()
    except Exception as e:
        st.markdown(race_error_card(e), unsafe_allow_html=True)
    st.stop()

def render_race_tab():
    race_pick = st.radio("Race", ["STOCKS", "CRYPTO"], horizontal=True, label_visibility="collapsed", key="race_pick")
    rc = next(r for r in race.ALL_RACES.values() if r["name"] == race_pick)
    now_utc = datetime.now(timezone.utc)
    rdoc = None
    if rc["key"] not in race.ENABLED:
        st.markdown('<div class="card sub">The crypto race is switched off for now: only the ASX race is running.</div>', unsafe_allow_html=True)
    else:
        try:
            rdoc = race.load_race(rc, create=False)  # repairs and saves any account left over from older rules
            rdoc = race.with_defaults(rdoc) if rdoc else None
        except Exception:
            rdoc = None
        if not rdoc:
            st.markdown('<div class="card sub">The race starts on the next bot run.</div>', unsafe_allow_html=True)
    if rdoc:
        table = race.standings(rdoc)
        champ = rdoc.get("champion")
        st.markdown(f'<div class="sub" style="margin-bottom:6px">Paper money · {rc["broker"]} fees · ranked by time-weighted return</div>', unsafe_allow_html=True)
        accts = rdoc["accounts"]
        lead_n = table[0][0]
        bench_r = race.twr(accts[race.BENCH])
        movers = [n for n in race.RACERS if n != race.BENCH]
        beat = sum(1 for n in movers if race.twr(accts[n]) > bench_r)
        kpis = [("Leader", f"{swatch(lead_n)}{lead_n}", f"{race.twr(accts[lead_n]):+.2f}%"),
                ("Scorecard in", f"{race.days_left(rdoc, now_utc)} days", f"number {rdoc['scorecard']}"),
                ("Trades", str(sum(n_trades(accts[n]) for n in movers)), f"fees ${sum(accts[n].get('fees_paid', 0) for n in movers):,.2f}"),
                ("Beating Buy and Hold", f"{beat} of {len(movers)}", f"benchmark {bench_r:+.2f}%")]
        st.markdown('<div class="kpis">' + "".join(f'<div class="kpi"><div class="label">{k}</div><div class="num">{v}</div><div class="sub">{s}</div></div>'
                                                   for k, v, s in kpis) + '</div>', unsafe_allow_html=True)
        rows = "".join(lb_row(i, n, accts[n], champ) for i, (n, _) in enumerate(table, 1))
        st.markdown(f'<div class="card">{rows}</div>', unsafe_allow_html=True)
        hist = rdoc.get("history", [])
        xs = [pd.Timestamp(h["t"]).tz_convert(MEL) for h in hist]
        fig = go.Figure()
        for n, _ in table:
            fig.add_trace(go.Scatter(x=xs, y=[h["v"].get(n) for h in hist], mode="lines", name=n,
                                     line=dict(width=1.6, color=RACER_COLOR.get(n), dash="dot" if n == race.BENCH else "solid"),
                                     hovertemplate="%{y:$,.0f}"))
        grid_line = dict(gridcolor="rgba(58,63,71,0.45)", zeroline=False, showline=False, tickfont=dict(size=11))
        fig.update_layout(height=250, margin=dict(l=6, r=6, t=6, b=6), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#A7ADB6", size=11), hovermode="x unified", hoverlabel=dict(bgcolor="#111216", bordercolor="#3A3F47"),
                          showlegend=False, xaxis=grid_line, yaxis=dict(tickprefix="$", **grid_line))  # leaderboard colours are the legend
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.markdown('<div class="label">Racers · tap a card for trades and diary</div><div class="grid">' + "".join(bot_card(n, rdoc["accounts"][n], champ, now_utc) for n, _ in table) + '</div>', unsafe_allow_html=True)
        with st.expander("Risk manager · last 10 decisions"):
            st.markdown(risk_log_html(rdoc) or '<div class="sub">No decisions yet. It checks every trade a bot wants to open.</div>', unsafe_allow_html=True)
    st.markdown('<div class="label">Hall of Fame</div>', unsafe_allow_html=True)
    try:
        hof = get("system", "hall_of_fame", None) or []
    except Exception:
        hof = []
    past = [e for e in hof if e.get("race") == rc["key"]]
    if not past:
        ends = f" Scorecard {rdoc['scorecard']} lands {race.scorecard_end(rdoc).astimezone(MEL).strftime('%a %d %b')}." if rdoc else ""
        st.markdown(f'<div class="card sub">No scorecards yet.{ends}</div>', unsafe_allow_html=True)
    hof_rows = ""
    for e in reversed(past):
        label, win_pct, bench_pct = hof_view(e)
        bench = f' · Buy and Hold {bench_pct:+.1f}%' if bench_pct is not None else ""
        hof_rows += line(f'<b>{label}</b> <span class="sub">to {datetime.fromisoformat(e["end"]).astimezone(MEL).strftime("%d %b %Y")}{bench}</span>',
                         f'{swatch(e["winner"])}{e["winner"]} {win_pct:+.1f}%')
    if hof_rows:
        st.markdown(f'<div class="card">{hof_rows}</div>', unsafe_allow_html=True)

# ---------- Home ----------
with home:
    total = sum(pots.values())
    st.markdown(f'<div class="hero"><div class="sub">Hi {USER}</div><div class="big" style="margin-top:6px">${total:,.0f}</div>'
                f'<div class="sub">in your pots</div><div style="margin-top:10px">Today {money(total_pl)} '
                f'<span class="sub">&nbsp;{ups} up · {downs} down</span></div></div>', unsafe_allow_html=True)
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


with race_tab:
    try:
        render_race_tab()
    except Exception as e:
        st.markdown(race_error_card(e), unsafe_allow_html=True)

# ---------- Backtest ----------
BT_RACES = {"Instant (1% fee)": "crypto_instant", "Markets (0.1% fee)": "crypto_markets"}


def pct_cell(x):
    return "" if x is None else f"{round(x, 1) or 0.0:+.1f}%"  # no "-0.0%"


def money_cell(x):
    return "" if x is None else f"${x:,.2f}"


def bt_table(racers, part):
    rows = []
    for n in race.RACERS:
        r = (racers.get(n) or {}).get(part)
        if not r:
            continue
        rows.append({"Racer": n, "Final value": f"${r['final_value']:,.0f}", "Return": pct_cell(r["return_pct"]),
                     "vs Buy and Hold": "" if n == race.BENCH else pct_cell(r.get("vs_buy_and_hold_pct")), "Trades": r["trades"],
                     "Win rate": "" if r["win_rate_pct"] is None else f"{r['win_rate_pct']:.0f}%", "Avg win": money_cell(r["avg_win"]),
                     "Avg loss": money_cell(r["avg_loss"]), "Max drawdown": f"-{r['max_drawdown_pct']:.1f}%", "Fees": f"${r['fees']:,.2f}",
                     "Flag": (racers[n].get("flag") or "") if part == "test" else ""})
    return pd.DataFrame(rows)


def render_backtest_tab():
    bt = load_system("backtest_results", None)
    if not bt or not bt.get("races"):
        st.markdown('<div class="card sub">No backtest yet. It runs every Sunday night, or start it from GitHub Actions (backtest workflow).</div>',
                    unsafe_allow_html=True)
        return
    run = datetime.fromisoformat(bt["run"]).astimezone(MEL)
    pick = st.radio("Backtest race", ["STOCKS", "CRYPTO"], horizontal=True, label_visibility="collapsed", key="bt_pick")
    key = "stocks"
    if pick == "CRYPTO":
        fee_pick = st.radio("CoinSpot fee", list(BT_RACES), horizontal=True, key="bt_fee")
        key = BT_RACES[fee_pick]
    res = bt["races"].get(key)
    st.markdown(f'<div class="sub" style="margin-bottom:6px">Run {run.strftime("%a %d %b %Y, %H:%M")} · real yfinance prices · '
                f'same rules and fees as the live race · paper money only</div>', unsafe_allow_html=True)
    if not res:
        st.markdown('<div class="card sub">No results for this race in the latest backtest.</div>', unsafe_allow_html=True)
        return
    per = res["period"]
    d = lambda s: datetime.fromisoformat(s).astimezone(MEL).strftime("%d %b %Y")
    st.markdown(f'<div class="card">' + line("Practice (first 70%)", f'{d(per["start"])} to {d(per["split"])}')
                + line("Test (last 30%, unseen)", f'{d(per["split"])} to {d(per["end"])}') + '</div>', unsafe_allow_html=True)
    part = st.radio("Period", ["test", "practice"], horizontal=True, key="bt_part",
                    format_func={"test": "Test period", "practice": "Practice period"}.get)
    st.dataframe(bt_table(res["racers"], part), hide_index=True, width="stretch")
    st.markdown('<div class="sub">"Probably luck (overfit)" means it won in practice but lost on the unseen test data.</div>', unsafe_allow_html=True)
    ch = res.get("chart") or {}
    if ch.get("t"):
        xs = [pd.Timestamp(t).tz_convert(MEL) for t in ch["t"]]
        fig = go.Figure()
        for n in race.RACERS:
            fig.add_trace(go.Scatter(x=xs, y=ch["series"].get(n), mode="lines", name=n,
                                     line=dict(width=1.6, color=RACER_COLOR.get(n), dash="dot" if n == race.BENCH else "solid"),
                                     hovertemplate="%{y:$,.0f}"))
        grid_line = dict(gridcolor="rgba(58,63,71,0.45)", zeroline=False, showline=False, tickfont=dict(size=11))
        fig.update_layout(height=340, margin=dict(l=8, r=8, t=28, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#A7ADB6", size=11), hovermode="x unified", hoverlabel=dict(bgcolor="#111216", bordercolor="#3A3F47"),
                          title=dict(text="Test period: account value", font=dict(size=12)),
                          legend=dict(orientation="h", y=-0.18, font=dict(size=11)), xaxis=grid_line, yaxis=dict(tickprefix="$", **grid_line))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    rm = res.get("risk_manager") or {}
    st.markdown("#### Risk Manager")
    verdict = "".join(line(f'{p_.title()} period', f'{rm[p_]["verdict"]}: bots {rm[p_]["avg_return_with_pct"]:+.1f}% with it, '
                                                    f'{rm[p_]["avg_return_without_pct"]:+.1f}% without') for p_ in ("practice", "test") if rm.get(p_))
    by_bot = ", ".join(f"{b} {k}" for b, k in sorted(rm.get("by_bot", {}).items(), key=lambda x: -x[1])) or "none"
    st.markdown(f'<div class="card">' + line("Trades it would have blocked", f'{rm.get("blocked", 0)}') + line("By racer", by_bot) + verdict
                + f'<div class="sub" style="margin-top:6px">{rm.get("note", "")}</div></div>', unsafe_allow_html=True)
    cp = res.get("coach") or {}
    st.markdown("#### Coach's Picks <span class=\"sub\">(rule-based estimate)</span>", unsafe_allow_html=True)
    t_, p_ = cp.get("test"), cp.get("practice")
    st.markdown(f'<div class="card">' + line("Weeks with picks", f'{cp.get("weeks_with_picks", 0)} of {cp.get("weeks", 0)} ({cp.get("picks", 0)} picks)')
                + (line("Practice return", pct_cell(p_["return_pct"])) if p_ else "")
                + (line("Test return", f'{pct_cell(t_["return_pct"])} ({pct_cell(t_.get("vs_buy_and_hold_pct"))} vs Buy and Hold)') if t_ else "")
                + '<div class="sub" style="margin-top:6px">Rule-based estimate: the best-scoring signals each Monday after fees, 0 to 3 picks, '
                  'cash saved when nothing qualifies. The real Coach uses AI, which may already know past prices, so it can&#39;t be replayed.</div></div>',
                unsafe_allow_html=True)
    sh = bt.get("shadow") or {}
    st.markdown("#### Shadow bot")
    if sh.get("error"):
        st.markdown(f'<div class="card sub">{sh["error"]}</div>', unsafe_allow_html=True)
    elif not sh.get("holdings"):
        st.markdown('<div class="card sub">No holdings with a purchase date to replay. Your real holdings are never touched.</div>', unsafe_allow_html=True)
    else:
        rows = ""
        for h in sh["holdings"]:
            what = "held all the way" if not h["sold"] else f'sold {h["sold"]["date"]} at ${h["sold"]["price"]:,.2f}'
            if h.get("bought_instead"):
                b = h["bought_instead"]
                what += f', bought {b["shares"]} {b["ticker"].replace(".AX", "")} {b["date"]}'
            elif h["sold"]:
                what += ", kept the cash"
            rows += line(f'<b>{h["ticker"].replace(".AX", "")}</b> <span class="sub">{what}</span>', money(h["difference"]))
        diff = sh["shadow_total"] - sh["hold_total"]
        st.markdown(f'<div class="card">' + line("Shadow bot", f'${sh["shadow_total"]:,.0f}') + line("Just holding", f'${sh["hold_total"]:,.0f}')
                    + line("Difference", money(diff)) + '</div>' + f'<div class="card">{rows}</div>'
                    + (f'<div class="sub">Skipped (no purchase date or no price data): {", ".join(sh["skipped"])}</div>' if sh.get("skipped") else ""),
                    unsafe_allow_html=True)
    st.markdown("#### Summary")
    st.markdown('<div class="card">' + "".join(f'<div style="margin:4px 0">{s}</div>' for s in bt.get("summary", [])) + '</div>', unsafe_allow_html=True)


with bt_tab:
    try:
        render_backtest_tab()
    except Exception as e:
        print("Backtest section failed:", repr(e))
        st.markdown('<div class="card sub">The backtest results couldn&#39;t load right now.</div>', unsafe_allow_html=True)

# ---------- Suggestions ----------
def claude_prompt(s, when):
    return (f"In the Iron Paw repo (hintzt-beep/asx-hub), change {s['bot']}'s rules in the {s['race'].upper()} race "
            f"(the bots are in bots.py, the shared rules in race.py): {s['change']}\n"
            f"Why, from the Coach report on {when}: {s['why']}\n"
            f"Evidence: {s['trades']} closed trades ({s['confidence']} confidence).\n"
            "Paper money only. Keep every shared safety rule (stop loss on every position, max 25% per position, no trade if fees are "
            "over 2%, duplicate guard, loss brake) and the risk manager. Keep the change small, test with alerter.py --once and "
            "coach.py, then commit and push to main and report the files changed.")


def picks_html(entry):
    out = ""
    for key, res in entry.get("races", {}).items():
        rc = race.ALL_RACES[key]
        for o in res.get("picks", []):
            name = o["ticker"].replace(".AX", "").replace("-AUD", "")
            size = f'{o["units"]:.6f} at ${o["price"]:,.2f} AUD' if rc["crypto"] else f'{o["units"]} shares at ${o["price"]:,.2f}'
            out += (f'<div class="card"><div class="row"><b>{rc["name"]} · {name}</b>{pill("BUY")}</div>'
                    + line(f'{rc["broker"]} order', f'about ${o["dollars"]:,.2f} ({size})') + line("Stop loss", f'${o["stop"]:,.2f}')
                    + line("Fee", f'${o["fee"]:,.2f}') + f'<div class="sub" style="margin-top:6px">{o["reason"]}</div></div>')
        if not res.get("picks"):
            out += f'<div class="card sub"><b>{rc["name"]}:</b> no picks this week. {res.get("no_pick_reason", "")} Saving ${res.get("cash", 0):,.2f}.</div>'
        for p in res.get("dropped", []):
            out += f'<div class="card sub"><b>{rc["name"]} · {p["ticker"]}</b> was suggested but not placed: {p["why"]}.</div>'
    return out


with sugg:
    reports = load_system("coach_reports", [])
    if not reports:
        st.markdown('<div class="card sub">No Coach reports yet. The Coach writes one each day at 5:30pm Melbourne.</div>', unsafe_allow_html=True)
    else:
        rep_ = reports[-1]
        when = datetime.fromisoformat(rep_["time"]).astimezone(MEL).strftime("%a %d %b, %H:%M")
        lists = "".join(f'<div class="label">{t}</div>' + "".join(f'<div class="sub">· {x}</div>' for x in rep_.get(k, []))
                        for t, k in (("What's working", "working"), ("What isn't", "not_working")) if rep_.get(k))
        st.markdown(f'<div class="card"><div class="row"><b style="font-size:1.1rem">Coach report</b><span class="sub">{when}</span></div>'
                    f'<div style="margin-top:6px">{rep_["summary"]}</div>{lists}</div>', unsafe_allow_html=True)
        st.markdown("#### Suggestions")
        if not rep_.get("suggestions"):
            st.markdown('<div class="card sub">No rule changes suggested in this report.</div>', unsafe_allow_html=True)
        for s in rep_.get("suggestions", []):
            st.markdown(f'<div class="card"><div class="row"><b>{swatch(s["bot"])}{s["bot"]} · {s["race"].upper()}</b>'
                        f'<span class="sub">{s["trades"]} trades · {s["confidence"]} confidence</span></div>'
                        f'<div style="margin-top:6px"><b>Change:</b> {s["change"]}</div><div class="sub" style="margin-top:4px">Why: {s["why"]}</div></div>',
                        unsafe_allow_html=True)
            status = s.get("status", "new")
            if status == "new":
                b1, b2 = st.columns(2)
                for btn, new_status in ((b1, "approved"), (b2, "dismissed")):
                    if btn.button("Approve" if new_status == "approved" else "Dismiss", key=f"{new_status}-{s['id']}"):
                        fresh = load_system("coach_reports", [])
                        for r_ in fresh:
                            for x in r_.get("suggestions", []):
                                if x.get("id") == s["id"]:
                                    x["status"] = new_status
                        try:
                            put("system", "coach_reports", fresh)
                        except Exception:
                            st.error("Could not save. Try again.")
                        st.rerun()
            elif status == "approved":
                st.markdown('<div class="sub">Approved. Nothing changes until you run this prompt in Claude Code:</div>', unsafe_allow_html=True)
                st.code(claude_prompt(s, when), language=None)
            else:
                st.markdown('<div class="sub">Dismissed.</div>', unsafe_allow_html=True)
    st.markdown("#### This week's Coach's Picks")
    picks = load_system("coach_picks", [])
    if picks:
        st.markdown(f'<div class="sub" style="margin-bottom:6px">Week {picks[-1]["week"]} · paper trades in the Coach\'s Picks account</div>'
                    + picks_html(picks[-1]), unsafe_allow_html=True)
    else:
        st.markdown('<div class="card sub">No picks yet. The Coach picks on Monday at 9:30am Melbourne.</div>', unsafe_allow_html=True)
    if len(reports) > 1:
        st.markdown("#### Past reports")
        for r_ in reversed(reports[:-1]):
            with st.expander(datetime.fromisoformat(r_["time"]).astimezone(MEL).strftime("%a %d %b, %H:%M")):
                st.markdown(r_["summary"])
                for s in r_.get("suggestions", []):
                    st.markdown(f"- **{s['bot']} ({s['race']})**: {s['change']} ({s['trades']} trades, {s['confidence']} confidence, {s.get('status', 'new')})")

# ---------- Portfolio ----------
with port:
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

# ---------- Insiders ----------
with insiders:
    st.markdown('<div class="sub">US politicians\' trades from public filings, reported days or weeks later. Data: Bargo Congress Trades.</div>', unsafe_allow_html=True)
    try:
        trades = celeb_trades()
    except Exception as e:
        trades = []
        st.warning(f"Couldn't load right now: {e}")
    ins_html = ""
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
        ins_html += mini(f'{pill(w)} <b>{tick or "?"}</b><br><span class="sub">{who} ({tag})</span>',
                         f'{pick(t, "amount", "amount_range", "range")}<br><span class="sub">{pick(t, "transaction_date", "traded", "trade_date", "date")}</span>')
    if ins_html:
        st.markdown(f'<div class="card">{ins_html}</div>', unsafe_allow_html=True)
    if trades:
        with st.expander("Raw data (for fixing)"):
            st.json(trades[0])

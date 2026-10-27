"""Strategy Lab: tests thousands of rule combinations on real daily price history and keeps only the ones that hold up.

Paper money only. Prices from yfinance daily bars (about 6 years). For each market (STOCKS: the 30 ASX race shares;
CRYPTO: the 12 AUD coins) every combination of an entry rule, a market filter and an exit rule is replayed:

  - a signal is seen at a day's close and bought at the NEXT day's open (no peeking at the future)
  - 0.1% slippage both ways, real fees (CommSec tiers for shares; CoinSpot Markets 0.1% and Instant 1% for crypto),
    no trade if fees are over 2% of it, max 25% of the account per position (so at most 4 at once)
  - stops are checked against each day's low, targets against its high (if both could hit on one day, the stop wins)

The history is split: practice (first 70%) and test (last 30%, unseen). A strategy only "survives" if it
  1. beat Buy and Hold in practice with at least 20 trades and a worst drop under 35%, AND
  2. beat Buy and Hold in the test period with at least 8 trades, AND
  3. beat the luck bar: its own copies with the buy days shifted to random dates (same exits, same number of signals,
     same time in the market, no timing skill). It must beat 95% of those 40 copies in the test period, AND
  4. beat Buy and Hold in BOTH halves of the test period (a lucky streak rarely lasts through both).
Only the 200 best practice performers per fee setting go through rules 2-4 (finalists).

Similar strategies tend to get lucky together, so a handful of survivors proves little. The verdict is "promising" only
with at least 5 survivors and 5x more than luck predicts. Calibrated on made-up prices (--synthetic): on pure noise
(6 runs) survivors never passed 3.6x luck; with a planted momentum edge (LAB_PLANT=0.3) they were about 11x luck.
Rule 3 is the guard against luck: test thousands of strategies and some look great by chance alone. The report also shows how
many finalists luck alone would get through: the share of the shifted copies that pass rules 2-4.

  python strategy_lab.py                 real prices, saves to Supabase (system/lab_results)
  python strategy_lab.py --synthetic     made-up random prices, for testing the engine (never saved)
"""
import argparse
import itertools
import json
import math
import os
import time
import zlib
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

import numpy as np
import pandas as pd

PRACTICE = 0.70
SLIP = 0.001
MAX_FEE_PCT = 0.02
MAX_POS = 0.25
MAX_OPEN = 4
START_CASH = 5000.0
MIN_TRADES_PRACTICE, MIN_TRADES_TEST, MAX_DD = 20, 8, 35.0
LUCK_PCTL, SHUFFLES, FINALISTS = 95, 40, 200
PROMISING_RATIO, PROMISING_MIN = 5, 5   # "promising" needs 5x more survivors than luck predicts, and at least 5      # each finalist is compared with 40 copies of itself whose buy days are shifted at random

STOCKS = ["ALL.AX", "ANZ.AX", "BHP.AX", "BOE.AX", "CBA.AX", "COL.AX", "CSL.AX", "EVN.AX", "FMG.AX", "GMG.AX",
          "IGO.AX", "LYC.AX", "MIN.AX", "MQG.AX", "NAB.AX", "NST.AX", "PDN.AX", "PLS.AX", "QBE.AX", "REA.AX",
          "RIO.AX", "STO.AX", "TCL.AX", "TLS.AX", "WBC.AX", "WDS.AX", "WES.AX", "WOW.AX", "WTC.AX", "XRO.AX"]
CRYPTO = ["BTC-AUD", "ETH-AUD", "SOL-AUD", "XRP-AUD", "BNB-AUD", "ADA-AUD", "DOGE-AUD", "AVAX-AUD",
          "LINK-AUD", "DOT-AUD", "LTC-AUD", "BCH-AUD"]
MARKETS = {"stocks": {"name": "STOCKS", "tickers": STOCKS, "bench": "VAS.AX", "fees": {"commsec": None}},
           "crypto": {"name": "CRYPTO", "tickers": CRYPTO, "bench": "BTC-AUD", "fees": {"markets": 0.001, "instant": 0.01}}}
FEE_NAMES = {"commsec": "CommSec", "markets": "CoinSpot Markets 0.1%", "instant": "CoinSpot Instant 1%"}


def commsec(amount):
    return 5.0 if amount <= 1000 else 10.0 if amount <= 3000 else 19.95 if amount <= 10000 else None


def fee_of(mode, amount):
    return commsec(amount) if mode == "commsec" else amount * mode


# ---------- Strategy grid ----------
def entry_grid():
    out = []
    for n, vol in itertools.product((10, 20, 55), (0, 1.5, 2, 3)):
        out.append(("breakout", {"n": n, "vol": vol}))
    for lvl, tick, trend in itertools.product((25, 30, 35), (False, True), (False, True)):
        out.append(("oversold", {"rsi": lvl, "tick": tick, "trend": trend}))
    for (fast, slow), pull in itertools.product(((20, 50), (50, 200)), (False, True)):
        out.append(("trend", {"fast": fast, "slow": slow, "pull": pull}))
    for vol, band in itertools.product((False, True), (False, True)):
        out.append(("cross", {"vol": vol, "band": band}))
    for drop, tick in itertools.product((5, 10, 15), (False, True)):
        out.append(("dip", {"drop": drop, "tick": tick}))
    return [(fam, p, regime) for fam, p in out for regime in (False, True)]


EXITS = [{"stop": s, "target": t, "trail": tr, "hold": h}
         for s, t, tr, h in itertools.product((0.05, 0.08, 0.12, 0.20), (None, 0.10, 0.25), (None, 0.10, 0.20), (10, 40, None))]


def describe(fam, p, regime, ex):
    e = {"breakout": lambda: f"Buy a {p['n']}-day high breakout" + (f" on {p['vol']:g}x+ normal volume" if p["vol"] else ""),
         "oversold": lambda: f"Buy when RSI is under {p['rsi']}" + (" and the price ticks up" if p["tick"] else "") + (" in a long uptrend (above the 200-day)" if p["trend"] else ""),
         "trend": lambda: f"Buy when price is above the {p['fast']}-day and {p['fast']}-day is above the {p['slow']}-day (rising)" + (", on a dip to the 20-day" if p["pull"] else ""),
         "cross": lambda: "Buy a fresh golden cross (20-day over the 50-day)" + (" with rising volume" if p["vol"] else "") + (" and RSI 50-70" if p["band"] else ""),
         "dip": lambda: f"Buy after a {p['drop']}%+ drop in 10 days" + (" once the price ticks up" if p["tick"] else ""),
         "random": lambda: "Buy on random days (luck test)"}[fam]()
    if regime:
        e += ", only when the market is above its 200-day average"
    x = [f"stop {ex['stop'] * 100:g}%"]
    if ex["target"]:
        x.append(f"take profit at +{ex['target'] * 100:g}%")
    if ex["trail"]:
        x.append(f"trailing stop {ex['trail'] * 100:g}%")
    x.append(f"sell after {ex['hold']} days" if ex["hold"] else "no time limit")
    return f"{e}. Exit: {', '.join(x)}."


# ---------- Indicators (computed once per ticker) ----------
def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def features(df, regime):
    c, h, v = df["Close"], df["High"], df["Volume"]
    f = {"rsi": rsi(c).fillna(50).values, "up": (c > c.shift(1)).values, "c": c.values}
    for n in (10, 20, 55):
        f[f"hi{n}"] = h.rolling(n).max().shift(1).values
    f["volr"] = (v / v.rolling(20).mean().shift(1)).replace([np.inf, -np.inf], np.nan).fillna(0).values
    for n in (20, 50, 200):
        s = c.rolling(n).mean()
        f[f"sma{n}"], f[f"sma{n}_10"] = s.values, s.shift(10).values
    f["s20_3"], f["s50_3"] = c.rolling(20).mean().shift(3).values, c.rolling(50).mean().shift(3).values
    f["vol5"], f["vol20"] = v.rolling(5).mean().values, v.rolling(20).mean().values
    f["ret10"] = (c / c.shift(10) - 1).values
    f["regime"] = regime.reindex(df.index).ffill().fillna(False).astype(bool).values
    return f


def signal(f, fam, p, regime):
    with np.errstate(invalid="ignore"):
        c = f["c"]
        if fam == "breakout":
            s = (c > f[f"hi{p['n']}"]) & (f["volr"] >= p["vol"])
        elif fam == "oversold":
            s = f["rsi"] < p["rsi"]
            if p["tick"]:  # oversold yesterday (or now) and today closed higher
                s = (np.minimum(f["rsi"], np.roll(f["rsi"], 1)) < p["rsi"]) & f["up"]
            if p["trend"]:
                s = s & (c > f["sma200"])
        elif fam == "trend":
            fa, sl = f[f"sma{p['fast']}"], f[f"sma{p['slow']}"]
            s = (c > fa) & (fa > sl) & (fa > f[f"sma{p['fast']}_10"])
            if p["pull"]:
                s = s & (c <= f["sma20"] * 1.02)
        elif fam == "cross":
            s = (f["sma20"] > f["sma50"]) & (f["s20_3"] <= f["s50_3"])
            if p["vol"]:
                s = s & (f["vol5"] > f["vol20"])
            if p["band"]:
                s = s & (f["rsi"] >= 50) & (f["rsi"] <= 70)
        elif fam == "dip":
            s = f["ret10"] <= -p["drop"] / 100
            if p["tick"]:
                s = s & f["up"]
        else:
            raise ValueError(fam)
        if regime:
            s = s & f["regime"]
    s = np.nan_to_num(s.astype(float)).astype(bool)
    s[:200] = False  # warm-up: every indicator needs history
    return s


# ---------- Trades for one ticker ----------
def trades_for(arr, sig, ex):
    """arr: dict of O/H/L/C numpy arrays. Signal on day i's close -> buy at day i+1's open. Returns (entry_i, exit_i, entry_px, exit_px)."""
    O, H, L, C = arr["O"], arr["H"], arr["L"], arr["C"]
    n, out = len(C), []
    idx = np.flatnonzero(sig[:-1])
    nxt = 0
    for i in idx:
        if i < nxt:
            continue
        e = i + 1
        px = O[e]
        if not px > 0:
            continue
        stop0 = px * (1 - ex["stop"])
        last = n - 1 if ex["hold"] is None else min(n - 1, e + ex["hold"] - 1)
        Hw, Lw, Ow = H[e:last + 1], L[e:last + 1], O[e:last + 1]
        lvl = np.full(len(Hw), stop0)
        if ex["trail"]:
            prev_hi = np.concatenate(([px], np.maximum.accumulate(Hw)[:-1]))
            lvl = np.maximum(lvl, prev_hi * (1 - ex["trail"]))
        hit_s = np.flatnonzero(Lw <= lvl)
        ks = hit_s[0] if len(hit_s) else None
        kt = None
        if ex["target"]:
            hit_t = np.flatnonzero(Hw >= px * (1 + ex["target"]))
            kt = hit_t[0] if len(hit_t) else None
        if ks is not None and (kt is None or ks <= kt):
            k, xp = ks, min(lvl[ks], Ow[ks])
        elif kt is not None:
            k, xp = kt, max(px * (1 + ex["target"]), Ow[kt])
        else:
            k, xp = len(Hw) - 1, C[last]
        out.append((e, e + k, px, xp))
        nxt = e + k + 1
    return out


# ---------- Portfolio replay ----------
def portfolio(trades, mode, t0, t1):
    """trades: list of (entry_day, exit_day, entry_px, exit_px). Trades that open in [t0, t1) count and run to their own exit."""
    tr = sorted(t for t in trades if t0 <= t[0] < t1)
    cash, open_, eq_hist, wins, n, fees = START_CASH, [], [START_CASH], 0, 0, 0.0
    events = []
    for k, t in enumerate(tr):
        events.append((t[0], 1, k))
        events.append((t[1], 2, k))
    events.sort()
    held = {}
    for when, kind, k in events:
        t = tr[k]
        if kind == 1:
            if len(held) >= MAX_OPEN:
                continue
            equity = cash + sum(v[0] for v in held.values())
            budget = min(MAX_POS * equity, cash)
            fill = t[2] * (1 + SLIP)
            if mode == "commsec":
                budget = min(budget, 10000.0, cash - 19.95)
            else:
                budget = min(budget, cash / (1 + mode))
            if budget <= 0:
                continue
            units = budget / fill if mode != "commsec" else math.floor(budget / fill)
            cost = units * fill
            if units <= 0 or cost <= 0:
                continue
            f = fee_of(mode, cost)
            if f is None or f > MAX_FEE_PCT * cost or cost + f > cash + 1e-6:
                continue
            cash -= cost + f
            fees += f
            held[k] = (cost + f, units)
        elif k in held:
            basis, units = held.pop(k)
            proceeds = units * t[3] * (1 - SLIP)
            f = fee_of(mode, proceeds)
            f = 19.95 if f is None else f
            cash += proceeds - f
            fees += f
            n += 1
            wins += proceeds - f > basis
            eq_hist.append(cash + sum(v[0] for v in held.values()))
    eq = np.array(eq_hist)
    dd = float(((np.maximum.accumulate(eq) - eq) / np.maximum.accumulate(eq)).max() * 100) if len(eq) else 0.0
    final = cash + sum(v[0] for v in held.values())
    return {"return_pct": round((final / START_CASH - 1) * 100, 2), "trades": n, "win_rate": round(wins / n * 100, 1) if n else None,
            "max_drop_pct": round(dd, 1), "fees": round(fees, 2)}


def buy_and_hold(bench, mode, t0, t1):
    w = bench[(bench.index >= t0) & (bench.index < t1)]
    if len(w) < 2:
        return None
    first, last = float(w["Open"].iloc[0]) * (1 + SLIP), float(w["Close"].iloc[-1]) * (1 - SLIP)
    units = START_CASH * 0.98 / first
    f_in, f_out = (19.95 if x is None else x for x in (fee_of(mode, units * first), fee_of(mode, units * last)))
    final = START_CASH - units * first - f_in + units * last - f_out
    return round((final / START_CASH - 1) * 100, 2)


# ---------- Worker: one strategy, all tickers, every fee mode, both periods ----------
G = {}


def init_worker(payload):
    G.update(payload)


def run_one(job):
    sid, fam, p, regime, ex, seed = job
    all_tr = []
    for t, d in G["data"].items():
        sig = signal(d["F"], fam, p, regime)
        if seed:  # luck copy: same signals, moved to random dates (circular shift per share)
            rng = np.random.default_rng(seed * 100003 + zlib.crc32(t.encode()) % 100003 + sid * 7)
            n = len(sig) - 200  # shift only inside the usable part, so no signals are lost to the warm-up
            if n > 200:
                sig = sig.copy()
                sig[200:] = np.roll(sig[200:], int(rng.integers(50, n - 50)))
        idx = d["idx"]
        all_tr += [(idx[a], idx[b], pa, pb) for a, b, pa, pb in trades_for(d, sig, ex)]
    res = {}
    for mode_name, mode in G["fees"].items():
        md = mode if mode is not None else "commsec"
        res[mode_name] = {"practice": portfolio(all_tr, md, G["t0"], G["split"]), "test": portfolio(all_tr, md, G["split"], G["t1"]),
                          "test_a": portfolio(all_tr, md, G["split"], G["mid"]), "test_b": portfolio(all_tr, md, G["mid"], G["t1"])}
    return sid, res


# ---------- Data ----------
def load_real(tickers, bench):
    import yfinance as yf
    out = {}
    for t in tickers + [bench]:
        try:
            df = yf.download(t, period="6y", interval="1d", progress=False, auto_adjust=True)
        except Exception as e:
            print("Price fetch failed:", t, e)
            continue
        if df is None or not len(df):
            print("No data:", t)
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
        out[t] = df[df["Close"] > 0]
    return out


def load_synthetic(tickers, bench, days=1500, seed=int(os.environ.get("LAB_SEED", "7"))):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=days)
    out = {}
    plant = float(os.environ.get("LAB_PLANT", "0"))  # tests only: a planted momentum edge (0 = pure noise)
    for t in tickers + [bench]:
        r = rng.normal(0.0003, 0.02, days)
        if plant:
            for i in range(20, days):
                r[i] += plant * r[i - 20:i].mean()
        c = 50 * np.exp(np.cumsum(r))
        o = c * np.exp(rng.normal(0, 0.005, days))
        h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.008, days)))
        l = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.008, days)))
        out[t] = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": rng.integers(1e5, 1e6, days).astype(float)}, index=idx)
    return out


# ---------- One market ----------
def run_market(key, prices, workers, limit=None):
    m = MARKETS[key]
    bench = prices.get(m["bench"])
    if bench is None:
        return {"error": f"No price data for {m['bench']}."}
    regime = bench["Close"] > bench["Close"].rolling(200).mean()
    data = {}
    for t in m["tickers"]:
        df = prices.get(t)
        if df is None or len(df) < 260:
            continue
        data[t] = {"O": df["Open"].values, "H": df["High"].values, "L": df["Low"].values, "C": df["Close"].values,
                   "idx": df.index.values.astype("datetime64[D]").astype(np.int64), "F": features(df, regime)}
    if not data:
        return {"error": "No usable price data."}
    days = np.unique(np.concatenate([d["idx"] for d in data.values()]))
    days = days[days >= days[0] + 200]  # the first 200 days are indicator warm-up
    t0, t1 = int(days[0]), int(days[-1]) + 1
    split = int(days[int(len(days) * PRACTICE)])
    mid = int(days[int(len(days) * (PRACTICE + (1 - PRACTICE) / 2))])
    jobs, meta = [], {}
    grid = [(fam, p, rg, ex) for (fam, p, rg) in entry_grid() for ex in EXITS]
    if limit:
        grid = grid[::max(1, len(grid) // limit)]
    for sid, (fam, p, rg, ex) in enumerate(grid):
        jobs.append((sid, fam, p, rg, ex, 0))
        meta[sid] = (fam, p, rg, ex)
    payload = {"data": data, "fees": m["fees"], "t0": t0, "split": split, "mid": mid, "t1": t1}
    started = time.time()
    results = run_jobs(jobs, payload, workers)
    bh_all = {}
    for mode_name, mode in m["fees"].items():
        md = mode if mode is not None else "commsec"
        bh_all[mode_name] = {"practice": buy_and_hold(bench, md, pd.Timestamp(day_s(t0)), pd.Timestamp(day_s(split))),
                             "test": buy_and_hold(bench, md, pd.Timestamp(day_s(split)), pd.Timestamp(day_s(t1 - 1)) + pd.Timedelta(days=1)),
                             "test_a": buy_and_hold(bench, md, pd.Timestamp(day_s(split)), pd.Timestamp(day_s(mid))),
                             "test_b": buy_and_hold(bench, md, pd.Timestamp(day_s(mid)), pd.Timestamp(day_s(t1 - 1)) + pd.Timedelta(days=1))}
    finalists = set()
    for mn in m["fees"]:
        ok = sorted((sid for sid, r in results.items() if passes_practice(r[mn], bh_all[mn])), key=lambda x: -results[x][mn]["practice"]["return_pct"])
        finalists.update(ok[:FINALISTS])
    finalists = sorted(finalists)
    luck_jobs = [((sid, k), *meta[sid], k) for sid in finalists for k in range(1, SHUFFLES + 1)]
    luck = {}
    for (sid, k), res in run_jobs([(sid, *rest) for (sid, k), *rest in luck_jobs], payload, workers, keep_order=True, keys=[x[0] for x in luck_jobs]):
        luck.setdefault(sid, []).append(res)
    secs = time.time() - started
    out = {"name": m["name"], "tickers": len(data), "period": {"start": day_s(t0), "split": day_s(split), "mid": day_s(mid), "end": day_s(t1 - 1)},
           "seconds": round(secs), "tested": len(grid), "fees": {}}
    for mode_name in m["fees"]:
        out["fees"][mode_name] = select(results, luck, meta, mode_name, bh_all[mode_name])
    return out


def day_s(x):
    return str(np.datetime64(int(x), "D"))


def run_jobs(jobs, payload, workers, keep_order=False, keys=None):
    """Run strategy jobs (in parallel when there are several CPUs). Returns {sid: result}, or (key, result) pairs if keys given."""
    if workers > 1:
        with ProcessPoolExecutor(workers, initializer=init_worker, initargs=(payload,)) as pool:
            res = list(pool.map(run_one, jobs, chunksize=16))
    else:
        init_worker(payload)
        res = [run_one(j) for j in jobs]
    if keys is not None:
        return [(k, r) for k, (_, r) in zip(keys, res)]
    return dict(res)


def base_test(r, bh):
    """Rules 2 and 4: beat Buy and Hold on unseen data with enough trades, and in both halves of it."""
    z = lambda x: x if x is not None else 0.0
    return (r["test"]["trades"] >= MIN_TRADES_TEST and r["test"]["return_pct"] > z(bh["test"])
            and r["test_a"]["return_pct"] > z(bh["test_a"]) and r["test_b"]["return_pct"] > z(bh["test_b"]))


def passes_practice(r, bh):
    p, bh_p = r["practice"], (bh["practice"] if bh["practice"] is not None else 0.0)
    return p["trades"] >= MIN_TRADES_PRACTICE and p["return_pct"] > bh_p and p["max_drop_pct"] <= MAX_DD


def select(results, luck, meta, mode_name, bh):
    bh_t = bh["test"] if bh["test"] is not None else 0.0
    real = [(sid, r[mode_name]) for sid, r in results.items()]

    def luck_bar(sid):
        rets = [x[mode_name]["test"]["return_pct"] for x in luck.get(sid, [])]
        return float(np.percentile(rets, LUCK_PCTL)) if len(rets) >= 10 else None

    base = lambda r: base_test(r, bh)

    def passes_test(sid, r):
        lb = luck_bar(sid)
        return base(r) and lb is not None and r["test"]["return_pct"] > lb

    practice_ok = sorted(((sid, r) for sid, r in real if passes_practice(r, bh)), key=lambda x: -x[1]["practice"]["return_pct"])
    finalists = practice_ok[:FINALISTS]
    beat_bh = [(sid, r) for sid, r in finalists if base(r)]
    survivors = [(sid, r) for sid, r in finalists if passes_test(sid, r)]
    expected = 0.0
    for sid, _ in finalists:  # how often a no-skill copy of this finalist gets through rules 2-4
        copies, lb = [x[mode_name] for x in luck.get(sid, [])], luck_bar(sid)
        if copies and lb is not None:
            expected += sum(1 for c in copies if base(c) and c["test"]["return_pct"] > lb) / len(copies)
    expected = round(expected, 1)
    score = lambda r: r["test"]["return_pct"] / max(r["test"]["max_drop_pct"], 5.0)
    survivors.sort(key=lambda x: -score(x[1]))
    if len(survivors) >= max(PROMISING_MIN, PROMISING_RATIO * expected):
        verdict = "promising"
    elif survivors:
        verdict = "weak"
    else:
        verdict = "none"

    def card(sid, r):
        fam, p, rg, ex = meta[sid]
        return {"id": sid, "family": fam, "params": p, "regime": rg, "exit": ex, "plain": describe(fam, p, rg, ex),
                "practice": r["practice"], "test": r["test"],
                "test_vs_buy_and_hold_pct": round(r["test"]["return_pct"] - bh_t, 2), "luck_bar_pct": luck_bar(sid)}

    fams = {}
    for sid, r in real:
        fam = meta[sid][0]
        best = fams.get(fam)
        if best is None or r["test"]["return_pct"] > best["test_return_pct"]:
            fams[fam] = {"test_return_pct": r["test"]["return_pct"], "plain": describe(*meta[sid])}
    return {"fee_name": FEE_NAMES[mode_name], "buy_and_hold": bh, "verdict": verdict,
            "counts": {"tested": len(real), "passed_practice": len(practice_ok), "finalists": len(finalists), "beat_buy_and_hold_in_test": len(beat_bh),
                       "survived": len(survivors), "expected_by_luck": expected},
            "survivors": [card(s, r) for s, r in survivors[:15]],
            "practice_stars_that_failed": [card(s, r) for s, r in finalists if not passes_test(s, r)][:5],
            "best_by_family": fams}


VERDICT = {"promising": "Far more survivors than luck explains. Worth paper-trading the best ones live.",
           "weak": "Some survivors, but not clearly more than luck could give. Treat with suspicion.",
           "none": "Nothing beat Buy and Hold and the luck test on unseen data. Buy and Hold wins here."}


def summary(res):
    lines = []
    for key, m in res["markets"].items():
        if m.get("error"):
            lines.append(f"{key.upper()}: {m['error']}")
            continue
        for mode, r in m["fees"].items():
            c, bh = r["counts"], r["buy_and_hold"]
            head = (f"{m['name']} ({r['fee_name']}): tested {c['tested']:,}; {c['passed_practice']:,} beat Buy and Hold in practice; "
                    f"{c['survived']} of the top {c['finalists']} also won on unseen data, in both halves, and beat the luck test (luck alone would give about {c['expected_by_luck']:g}).")
            if bh["test"] is not None:
                head += f" Buy and Hold made {bh['test']:+.1f}% in the test period."
            lines.append(head)
            lines.append("  " + VERDICT[r["verdict"]])
            if r["survivors"]:
                s = r["survivors"][0]
                lines.append(f"  Best: {s['plain']} Test {s['test']['return_pct']:+.1f}% over {s['test']['trades']} trades, worst drop {s['test']['max_drop_pct']:.0f}%.")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true", help="made-up prices to test the engine; never saved")
    ap.add_argument("--limit", type=int, default=None, help="test only about this many strategies per market (quick run)")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--out", default=None, help="also write the result JSON here")
    a = ap.parse_args()
    res = {"run": datetime.now(timezone.utc).isoformat(), "synthetic": a.synthetic, "start_cash": START_CASH,
           "rules": {"practice_share": PRACTICE, "min_trades_practice": MIN_TRADES_PRACTICE, "min_trades_test": MIN_TRADES_TEST,
                     "max_drop_pct": MAX_DD, "luck_percentile": LUCK_PCTL}, "markets": {}}
    for key, m in MARKETS.items():
        prices = load_synthetic(m["tickers"], m["bench"]) if a.synthetic else load_real(m["tickers"], m["bench"])
        print(f"{m['name']}: {len(prices)} price series loaded")
        res["markets"][key] = run_market(key, prices, a.workers, a.limit)
        print(f"{m['name']}: done in {res['markets'][key].get('seconds', 0)}s")
    res["summary"] = summary(res)
    print("\n".join(res["summary"]))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1, default=str)
    if not a.synthetic and not a.no_save:
        from store import put
        put("system", "lab_results", json.loads(json.dumps(res, default=str)))
        print("Saved to system/lab_results")


if __name__ == "__main__":
    main()

"""The five racing bots. Each one trades by its own rules, explains every trade in its own voice
and keeps a short daily diary. Paper money only, real yfinance data only, shared safety rules from race.py."""
import pandas as pd

from race import MEL, STRATEGIES, buy, p, sell


# ---------- Indicators from real daily bars (None when there is not enough data) ----------
def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    down = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    return 100.0 if down == 0 else float(100 - 100 / (1 + up / down))


def atr(df, n=14):
    prev = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()], axis=1).max(axis=1)
    return float(tr.tail(n).mean())


def daily_view(mkt, t, need=60):
    cache = getattr(mkt, "views", None)
    if cache is not None and t in cache:
        v = cache[t]
    else:
        v = _daily_view(mkt, t)
        if cache is not None:
            cache[t] = v
    return v if v is not None and len(v["df"]) >= need else None


def _daily_view(mkt, t):
    df = mkt.daily(t)
    px = mkt.price(t)
    if df is None or len(df) < 20 or not px:
        return None
    c, v = df["Close"], df["Volume"]
    s20, s50 = c.rolling(20).mean(), c.rolling(50).mean()
    return {"px": px, "df": df, "close": c, "rsi": rsi(c), "atr": atr(df), "sma20": float(s20.iloc[-1]), "sma50": float(s50.iloc[-1]),
            "s20": s20, "s50": s50, "sma200": float(c.tail(200).mean()) if len(c) >= 200 else None,
            "vol5": float(v.tail(5).mean()), "vol20": float(v.tail(20).mean())}


def holding_words(a):
    names = [x["ticker"].replace(".AX", "").replace("-AUD", "") for x in a["positions"]]
    if names:
        return f"I'm holding {', '.join(names)}"
    if a.get("saving"):
        return "I'm holding cash and saving up: at this account size the fees (brokerage) would eat too much of any trade"
    return "I'm all in cash right now"


def are(n):
    return "is" if n == 1 else "are"


def today(now):
    return now.astimezone(MEL).date().isoformat()


class Bot:
    name = style = ""

    def trade(self, rc, a, name, mkt, now, events):
        for pos in list(a["positions"]):
            px = mkt.price(pos["ticker"])
            why = px and self.exit_reason(pos, px, mkt)
            if why:
                sell(rc, a, name, pos, px, why, now, events)
        seen, found = 0, []
        for t in rc["tickers"]:
            sig = self.signal(mkt, t, now)
            if sig is not False:
                seen += 1
            if sig:
                found.append((t, sig))
        found.sort(key=lambda x: -x[1].get("rank", 0))
        a["saving"] = False
        for t, sig in found:
            if not self.may_buy(a, now):
                break
            if buy(rc, a, name, t, sig["px"], sig["stop"], sig["reason"], now, events, frac=sig.get("frac", 0.25),
                   risk=sig.get("risk"), target=sig.get("target"), trail=sig.get("trail"), extra=sig.get("extra")):
                a["last_buy_day"] = today(now)
            elif any(k in a.get("last_reject", "") for k in ("limit 2%", "too small", "not enough cash")):
                a["saving"] = True  # a setup was there, but fees would be too big for a trade this account can make
        if a.get("diary", {}).get("day") != today(now):
            note = "I'm benched by the loss brake (down 15% from my peak), so no new buys until I recover or the next scorecard. " if a["benched"] else ""
            a["diary"] = {"day": today(now), "text": note + self.diary(a, seen, len(found))}

    def may_buy(self, a, now):
        return True

    def exit_reason(self, pos, px, mkt):
        return None

    def stop_reason(self, pos, px):
        return f"Stop loss (the safety exit that caps the loss) hit at ${p(px)}."

    def target_reason(self, pos, px):
        return f"Profit target (the planned exit price) reached at ${p(px)}."


class Tyler(Bot):
    name, style = "Tyler", "The Momentum Hunter: buys breakouts on strong volume, quick in and out."

    def signal(self, mkt, t, now):
        df = mkt.intraday(t)
        if df is None or len(df) < 12:
            return False
        if (df.index[-1] - df.index[-2]).total_seconds() >= 20 * 3600:
            day = df.tail(21)  # daily bars (backtests): "today's high" becomes the recent 20-day high
        else:
            day = df[df.index.date == df.index[-1].date()]
        if len(day) < 12:
            return None
        last, prior = day.iloc[-1], day.iloc[:-1]
        level, avg_vol = float(prior["High"].max()), float(prior["Volume"].mean())
        px = float(last["Close"])
        if avg_vol <= 0 or px <= level or float(last["Volume"]) / avg_vol <= 2:
            return None
        stop = float(prior["Low"].tail(6).min())
        if stop >= px:
            return None
        ratio, target = float(last["Volume"]) / avg_vol, px + 2 * (px - stop)
        return {"px": px, "stop": stop, "target": target, "rank": ratio, "extra": {"level": level},
                "reason": f"Breakout (momentum: buying what's already moving fast): ${p(px)} pushed above today's high of ${p(level)} "
                          f"on {ratio:.1f}x normal volume. Tight stop ${p(stop)}, target ${p(target)} (2x the risk)."}

    def exit_reason(self, pos, px, mkt):
        if pos.get("level") and px < pos["level"]:
            return f"Momentum fading (the move stalled): back under the ${p(pos['level'])} breakout level, so I'm out."
        return None

    def stop_reason(self, pos, px):
        return f"Stop loss (my safety exit just under the breakout) hit at ${p(px)}. The breakout failed, on to the next."

    def target_reason(self, pos, px):
        return f"Profit target hit at ${p(px)} (2x the risk I took). Banked it."

    def diary(self, a, seen, found):
        return (f"Scanned {seen} names for breakouts and {found} {are(found)} pushing through today's high on heavy volume. {holding_words(a)}. "
                "Momentum (buying what's already moving fast) only pays if I'm quick, so I'll keep hunting.")


class Ryan(Bot):
    name, style = "Ryan", "The Bargain Hunter: buys sharp drops when RSI is under 30, waits days for the bounce."

    def signal(self, mkt, t, now):
        v = daily_view(mkt, t)
        if v is None:
            return False
        drop = (v["px"] / float(v["close"].iloc[-6]) - 1) * 100
        if v["rsi"] >= 30 or drop > -5:
            return None
        stop = v["px"] * 0.92
        return {"px": v["px"], "stop": stop, "frac": 0.20, "rank": -v["rsi"],
                "reason": f"Oversold (RSI {v['rsi']:.0f}, under 30 means sold too hard): down {abs(drop):.1f}% in 5 days. "
                          f"Mean reversion (betting a big drop bounces back) says buy. Stop ${p(stop)}, selling near the 20-day average (${p(v['sma20'])})."}

    def exit_reason(self, pos, px, mkt):
        v = daily_view(mkt, pos["ticker"])
        if v and px >= v["sma20"]:
            return f"Back to the 20-day average (${p(v['sma20'])}): that's the bounce I was waiting for. Selling."
        return None

    def stop_reason(self, pos, px):
        return f"Stop loss (my wider safety exit, 8% down) hit at ${p(px)}. This one kept falling, so I'm out."

    def diary(self, a, seen, found):
        return (f"{found} of {seen} names {are(found)} oversold (RSI under 30) after a sharp drop. {holding_words(a)}. "
                "Mean reversion (betting a big drop bounces back) takes patience, so I'm happy to wait days for the bounce.")


class Nathan(Bot):
    name, style = "Nathan", "The Steady Hand: small bets on strong long-term uptrends, trailing stop, holds for weeks."

    def signal(self, mkt, t, now):
        v = daily_view(mkt, t, need=200)
        if v is None:
            return False
        rising = v["sma50"] > float(v["s50"].iloc[-11])
        if not (v["px"] > v["sma50"] > v["sma200"] and rising):
            return None
        stop = v["px"] * 0.92
        return {"px": v["px"], "stop": stop, "frac": 0.10, "trail": 0.08, "rank": v["px"] / v["sma200"],
                "reason": f"Trend following (riding a steady climb): ${p(v['px'])} is above the 50-day (${p(v['sma50'])}) and 200-day "
                          f"(${p(v['sma200'])}) averages and the 50-day is rising. Small position, trailing stop (rises with the price) from ${p(stop)}."}

    def may_buy(self, a, now):  # trades rarely: one new name a day, five at most
        return a.get("last_buy_day") != today(now) and len(a["positions"]) < 5

    def stop_reason(self, pos, px):
        return f"Trailing stop (the stop that rose with the price) hit at ${p(px)}. The climb paused, so I'm keeping what's left."

    def diary(self, a, seen, found):
        return (f"{found} of {seen} names {are(found)} in steady uptrends (above the 50 and 200-day averages). {holding_words(a)}. "
                "Trend following (riding a steady climb) means small bets, one new name a day at most, and letting winners run for weeks.")


class Newton(Bot):
    name, style = "Newton", "The Scientist: buys only when the golden cross, volume and RSI all agree; risks 1% a trade."

    def signal(self, mkt, t, now):
        v = daily_view(mkt, t)
        if v is None:
            return False
        s20, s50 = v["s20"], v["s50"]
        crossed = s20.iloc[-1] > s50.iloc[-1] and (s20.iloc[-4:-1] <= s50.iloc[-4:-1]).any()
        vol_up = v["vol5"] > v["vol20"]
        if not (crossed and vol_up and 50 <= v["rsi"] <= 70):
            return None
        stop = v["px"] - 2 * v["atr"]
        if stop <= 0:
            return None
        return {"px": v["px"], "stop": stop, "risk": 0.01, "rank": v["vol5"] / v["vol20"],
                "reason": f"Golden cross (20-day average crossing above the 50-day), volume rising ({v['vol5'] / v['vol20']:.1f}x) and RSI "
                          f"{v['rsi']:.0f} (inside 50-70). All three agree. Risk-based position sizing (a stop-out costs 1% of my account), stop ${p(stop)}."}

    def exit_reason(self, pos, px, mkt):
        v = daily_view(mkt, pos["ticker"])
        if v and v["sma20"] < v["sma50"]:
            return "Signals no longer agree: the 20-day average fell back under the 50-day (a death cross). The data says exit."
        return None

    def stop_reason(self, pos, px):
        return f"Stop loss (two average daily ranges below entry) hit at ${p(px)}. About a 1% loss, exactly as planned."

    def diary(self, a, seen, found):
        return (f"Tested {seen} names and {found} pass all three checks: golden cross, rising volume, RSI 50-70. {holding_words(a)}. "
                "No emotion, just numbers: I act only when the signals line up, and each bet risks 1% (risk-based position sizing).")


class Morpheus(Bot):
    name, style = "Morpheus", "The Contrarian: buys big into panic, sells into euphoria, few trades."

    def signal(self, mkt, t, now):
        v = daily_view(mkt, t)
        if v is None:
            return False
        rets = v["close"].pct_change()
        calm = float(rets.tail(60).std())
        fear = float(rets.tail(10).std()) / calm if calm > 0 else 0
        drop = (v["px"] / float(v["close"].iloc[-11]) - 1) * 100
        if drop > -10 or fear < 1.5:
            return None
        stop = v["px"] * 0.88
        return {"px": v["px"], "stop": stop, "frac": 0.25, "rank": fear,
                "reason": f"Buying when others panic (going against the crowd): down {abs(drop):.1f}% in 10 days with price swings "
                          f"{fear:.1f}x their usual size. The crowd is selling, so I'm buying big. Stop ${p(stop)}."}

    def may_buy(self, a, now):  # fewer, bigger bets
        return len(a["positions"]) < 2

    def exit_reason(self, pos, px, mkt):
        gain = (px / pos["entry"] - 1) * 100
        v = daily_view(mkt, pos["ticker"])
        if gain >= 10 or (v and v["rsi"] > 70):
            return f"Taking profit on euphoria (selling into the crowd's excitement): up {gain:.1f}%" + (f", RSI {v['rsi']:.0f}." if v else ".")
        return None

    def stop_reason(self, pos, px):
        return f"Stop loss (my 12% line in the sand) hit at ${p(px)}. The panic was right this time."

    def diary(self, a, seen, found):
        return (f"{found} of {seen} names {are(found)} in a panic: down 10%+ in ten days with wild swings. {holding_words(a)}. "
                "When the crowd is fearful I get greedy (buying when others panic), and I sell when they get euphoric.")


for _bot in (Tyler(), Ryan(), Nathan(), Newton(), Morpheus()):
    STRATEGIES[_bot.name] = _bot
STYLES = {n: b.style for n, b in STRATEGIES.items()}
STYLES["Buy and Hold"] = "The Benchmark: puts each deposit into one index as it arrives, never sells."
STYLES["Coach's Picks"] = "The Coach: up to 3 hand-picked trades a week with the new $400, or saves the cash."

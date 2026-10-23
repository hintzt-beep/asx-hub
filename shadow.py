"""Shadow-bot rules. Paper only: pure functions, no network, no orders, never writes holdings."""
from datetime import date, datetime

BROKERAGE = 10.0        # to sell
TAKE_PROFIT_PCT = 2.0   # sell a downtrend once the gain is over this
CUT_LOSS_PCT = 8.0      # sell if the loss is worse than this, whatever the trend
TAX_NOTE = " Held over 12 months, so the Australian tax discount applies."


def trend_word(score):
    return "BUY" if score >= 7 else "HOLD" if score >= 4 else "SELL"


def holding_key(h):
    return f"{h.get('ticker')}|{float(h.get('paid') or 0):g}|{float(h.get('qty') or 0):g}|{h.get('bought') or ''}"


def _m(x):
    return f"${abs(x):,.0f}"


def decide(qty, paid, price, score, bought=None, today=None):
    """HOLD or SELL for one holding, with a plain-English reason."""
    if not paid or paid <= 0 or not qty:
        return {"word": "HOLD", "gain": None, "pct": None, "reason": "Add what you paid to see a gain or loss and get a decision."}
    if score is None or price is None:
        return {"word": "HOLD", "gain": None, "pct": None, "reason": "No price data right now. Holding."}
    basis = qty * paid
    gain = qty * price - BROKERAGE - basis  # after $10 brokerage to sell
    pct = gain / basis * 100
    trend = trend_word(score)
    heading = "Trending up" if trend == "BUY" else "Steady" if trend == "HOLD" else "Trending down"
    up = gain > 0
    if pct < -CUT_LOSS_PCT:
        word, why = "SELL", f"Down {abs(pct):.1f}% ({_m(gain)} after costs), worse than the {CUT_LOSS_PCT:g}% limit. Cut the loss."
    elif trend == "SELL" and pct > TAKE_PROFIT_PCT:
        word, why = "SELL", f"Trending down and up {pct:.1f}% ({_m(gain)} after costs). Take the profit."
    elif trend == "SELL" and up:
        word, why = "HOLD", f"Trending down, but the gain is only {_m(gain)} after costs ({pct:.1f}%, it needs over {TAKE_PROFIT_PCT:g}% to sell)."
    elif trend == "SELL":
        word, why = "HOLD", f"Trending down, and you are down {_m(gain)} after costs ({abs(pct):.1f}%), not past the {CUT_LOSS_PCT:g}% limit yet. Holding."
    else:
        word, why = "HOLD", f"{heading}, and {'up' if up else 'down'} {_m(gain)} after costs ({abs(pct):.1f}%). Keep it."
    try:
        held = ((today or date.today()) - datetime.strptime(str(bought)[:10], "%Y-%m-%d").date()).days
    except ValueError:
        held = 0
    return {"word": word, "gain": gain, "pct": pct, "reason": why + (TAX_NOTE if held > 365 else "")}

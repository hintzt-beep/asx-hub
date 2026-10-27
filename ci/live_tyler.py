"""CI only: run Tyler's crypto lab rule against live yfinance prices (no database, no trades)."""
import sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.getcwd())
import types
fake = types.ModuleType("store"); fake.get = lambda o, n, d: d; fake.put = lambda *a: None
sys.modules["store"] = fake
import race, bots
T = bots.STRATEGIES["Tyler"]; T.crypto = True
m = race.Market(); now = datetime.now(timezone.utc)
btc = T.closed_days(m, "BTC-AUD", now)
print("BTC last closed bar:", btc.index[-1], "close", float(btc["Close"].iloc[-1]), "200d avg", float(btc["Close"].tail(200).mean()))
for t in race.CRYPTO:
    d = T.closed_days(m, t, now)
    sig = T.lab_signal(m, t, now)
    print(t, "last closed:", None if d is None else d.index[-1], "->", "BUY " + sig["reason"] if sig else sig)
print("ok")

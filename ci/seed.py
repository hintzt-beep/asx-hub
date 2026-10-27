"""CI only: build race docs with the real alerter against the fake store, then add sample trades so cards have content."""
import os, sys, runpy
from datetime import datetime, timezone
REPO = sys.argv[1]
sys.path.insert(0, os.path.dirname(__file__)); import fake_store
sys.modules["store"] = fake_store
sys.path.insert(0, REPO)
sys.argv = ["alerter.py", "--once"]
try:
    runpy.run_path(os.path.join(REPO, "alerter.py"), run_name="__main__")
except SystemExit:
    pass
now = datetime.now(timezone.utc).isoformat()
import json
fake_store.put("system", "lab_results", json.load(open(os.path.join(os.path.dirname(__file__), "lab_sample.json"))))
print("seeded lab_results")
for key in ("race_stocks", "race_crypto"):
    doc = fake_store.get("system", key, None)
    if not doc:
        print("no", key); continue
    a = doc["accounts"]["Tyler"]
    a["trades"].append({"time": now, "side": "BUY", "ticker": "BHP.AX", "price": 45.1, "shares": 2, "fee": 5.0,
                        "reason": "SAMPLE (CI only): breakout above today's high on 3.4x normal volume. Tight stop, target 2x the risk."})
    a["diary"] = {"day": datetime.now(timezone.utc).date().isoformat(), "text": "SAMPLE diary (CI only)."}
    doc.setdefault("risk_log", []).append({"time": now, "decision": "block", "bot": "Ryan", "ticker": "CBA.AX", "cost": 80.0,
                                            "reason": "SAMPLE (CI only): fees too large for this account size."})
    fake_store.put("system", key, doc)
    print("seeded", key)

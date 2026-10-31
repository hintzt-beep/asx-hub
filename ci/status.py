"""CI only: race standings, recent bot trades and the latest Coach report (paper race data only, no personal data)."""
import json
import race
from store import get
out = {"races": {}}
for key, rc in race.ALL_RACES.items():
    doc = get("system", rc["doc"], None)
    if not doc:
        continue
    doc = race.with_defaults(doc)
    rows = []
    for n, _ in race.standings(doc):
        a = doc["accounts"][n]
        sells = [t for t in a["trades"] if t["side"] == "SELL"]
        rows.append({"racer": n, "twr_pct": round(race.twr(a), 2), "value": round(race.value(a), 2), "put_in": a.get("contributed"),
                     "trades": sum(1 for t in a["trades"] if t["side"] in ("BUY", "SELL")), "closed": len(sells),
                     "wins": sum(1 for t in sells if t.get("pnl", 0) > 0), "holding": [x["ticker"] for x in a["positions"]],
                     "last": [{k: t.get(k) for k in ("time", "side", "ticker", "pnl")} for t in a["trades"][-3:]], "benched": a.get("benched")})
    out["races"][key] = {"scorecard": doc.get("scorecard"), "rows": rows,
                         "blocks": sum(1 for e in doc.get("risk_log", []) if e.get("decision") != "approve"),
                         "approvals": sum(1 for e in doc.get("risk_log", []) if e.get("decision") == "approve")}
rep = (get("system", "coach_reports", None) or [])[-1:]
out["coach"] = [{"time": r["time"], "summary": r.get("summary"), "suggestions": [{k: s.get(k) for k in ("bot", "race", "change", "status")}
                                                                                 for s in r.get("suggestions", [])]} for r in rep]
json.dump(out, open("suggestions.json", "w"), indent=1, default=str)

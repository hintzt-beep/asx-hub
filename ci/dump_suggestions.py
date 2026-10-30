"""CI only: copy the Coach's recent suggestions (bot, race, change, why, status) so they can be actioned. No personal data."""
import json
from store import get
reports = get("system", "coach_reports", None) or []
out = []
for r in reports[-6:]:
    out.append({"id": r.get("id"), "time": r.get("time"), "summary": r.get("summary"),
                "suggestions": [{k: s.get(k) for k in ("id", "bot", "race", "change", "why", "trades", "confidence", "status")}
                                for s in r.get("suggestions", [])]})
json.dump(out, open("suggestions.json", "w"), indent=1)
print(len(out), "reports")

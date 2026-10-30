"""CI only (one-off): mark every 'new' Coach suggestion as approved, at Ty's request (30 Oct). Writes only the status field."""
import json
from store import get, put
reports = get("system", "coach_reports", None) or []
n = 0
for r in reports:
    for s in r.get("suggestions", []):
        if s.get("status", "new") == "new":
            s["status"] = "approved"
            n += 1
put("system", "coach_reports", reports)
left = sum(1 for r in reports for s in r.get("suggestions", []) if s.get("status", "new") == "new")
json.dump({"approved": n, "still_new": left}, open("suggestions.json", "w"))
print("approved", n)

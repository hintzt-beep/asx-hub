"""CI only: a JSON-file stand-in for Supabase so the UI check never touches real data."""
import json, os
F = os.environ.get("FAKE_DB", "/tmp/fake_db.json")
def _db():
    try:
        return json.load(open(F))
    except Exception:
        return {}
def get(owner, name, default):
    return _db().get(f"{owner}/{name}", default)
def put(owner, name, data):
    d = _db(); d[f"{owner}/{name}"] = data; json.dump(d, open(F, "w"))

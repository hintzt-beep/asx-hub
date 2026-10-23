import os
import json
import urllib.request
import urllib.parse

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_KEY", "")


def _call(method, path, body=None, extra=None):
    headers = {"apikey": KEY, "Content-Type": "application/json"}
    if KEY.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {KEY}"
    headers.update(extra or {})
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{URL}/rest/v1/{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        text = r.read().decode("utf-8")
    return json.loads(text) if text else None


def get(owner, name, default):
    q = urllib.parse.urlencode({"owner": f"eq.{owner}", "name": f"eq.{name}", "select": "data"})
    rows = _call("GET", f"store?{q}")
    return rows[0]["data"] if rows else default


def put(owner, name, data):
    _call("POST", "store?on_conflict=owner,name", {"owner": owner, "name": name, "data": data},
          {"Prefer": "resolution=merge-duplicates,return=minimal"})
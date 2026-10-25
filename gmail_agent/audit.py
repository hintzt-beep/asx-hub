"""Activity log of every proposed and completed action, kept in Supabase (private), not in
the public GitHub logs. Entries hold message ids, labels and reasons only: no subjects,
senders or bodies.

Stored as one document: owner "Ty", name "gmail_audit", newest last, capped at MAX_ENTRIES.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

OWNER = "Ty"
DOC = "gmail_audit"
MAX_ENTRIES = 3000


class AuditError(Exception):
    """The log couldn't be read or saved. The agent stops before changing Gmail."""


class Store(Protocol):
    def get(self, owner: str, name: str, default): ...
    def put(self, owner: str, name: str, data) -> None: ...


class SupabaseStore:
    """Thin wrapper around the project's store.py (needs SUPABASE_URL / SUPABASE_KEY)."""

    def get(self, owner, name, default):
        import store
        return store.get(owner, name, default)

    def put(self, owner, name, data):
        import store
        store.put(owner, name, data)


class MemoryStore:
    """In-memory store for tests and for dry runs without Supabase."""

    def __init__(self):
        self.docs: dict[tuple[str, str], object] = {}

    def get(self, owner, name, default):
        return self.docs.get((owner, name), default)

    def put(self, owner, name, data):
        self.docs[(owner, name)] = data


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AuditLog:
    def __init__(self, store: Store):
        self.store = store
        self.entries: list[dict] = []

    def load(self) -> "AuditLog":
        try:
            data = self.store.get(OWNER, DOC, {"entries": []})
        except Exception as exc:  # network, auth, bad JSON
            raise AuditError(f"Couldn't read the activity log ({type(exc).__name__}).") from None
        self.entries = list((data or {}).get("entries", []))
        return self

    def save(self) -> None:
        self.entries = self.entries[-MAX_ENTRIES:]
        try:
            self.store.put(OWNER, DOC, {"entries": self.entries, "updated": now()})
        except Exception as exc:
            raise AuditError(f"Couldn't save the activity log ({type(exc).__name__}).") from None

    def applied_keys(self) -> set[tuple[str, str]]:
        """(message id, label) pairs the agent has added and not undone."""
        keys: set[tuple[str, str]] = set()
        for e in self.entries:
            k = (e.get("message_id"), e.get("value"))
            if e.get("status") == "applied" and e.get("kind") == "label":
                keys.add(k)
            elif e.get("status") == "undone":
                keys.discard(k)
        return keys

    def add(self, run_id: str, message_id: str, kind: str, value: str, status: str, reason: str = "") -> None:
        self.entries.append({"at": now(), "run": run_id, "message_id": message_id, "kind": kind,
                             "value": value, "status": status, "reason": reason[:200]})

    def runs(self) -> list[str]:
        seen: list[str] = []
        for e in self.entries:
            if e.get("status") == "applied" and e.get("run") not in seen:
                seen.append(e.get("run"))
        return seen

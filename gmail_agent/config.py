"""Settings, all from environment variables so no secret ever sits in the code."""
from __future__ import annotations

import os
from dataclasses import dataclass

# gmail.modify: read, add/remove labels, move to Spam/Trash. It can NOT permanently delete
# (that needs https://mail.google.com/, which this agent never asks for).
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
FORBIDDEN_SCOPE = "https://mail.google.com/"

TOKEN_URI = "https://oauth2.googleapis.com/token"


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


def _int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.environ.get(name, "").strip() or default)
    except ValueError:
        value = default
    return max(low, min(high, value))


@dataclass(frozen=True)
class Settings:
    enabled: bool          # master switch: GMAIL_AGENT_ENABLED=0 stops everything
    dry_run: bool          # no Gmail changes unless this is explicitly off
    query: str             # Gmail search for messages to look at
    max_messages: int      # cap per run, keeps API use small
    client_id: str
    client_secret: str
    refresh_token: str

    @property
    def has_credentials(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)


def load() -> Settings:
    return Settings(
        enabled=_flag("GMAIL_AGENT_ENABLED", True),
        dry_run=_flag("GMAIL_DRY_RUN", True),
        query=os.environ.get("GMAIL_QUERY", "").strip() or "newer_than:1d -in:chats",
        max_messages=_int("GMAIL_MAX_MESSAGES", 200, 1, 500),
        client_id=os.environ.get("GMAIL_CLIENT_ID", "").strip(),
        client_secret=os.environ.get("GMAIL_CLIENT_SECRET", "").strip(),
        refresh_token=os.environ.get("GMAIL_REFRESH_TOKEN", "").strip(),
    )

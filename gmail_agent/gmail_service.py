"""The only code that talks to Gmail. Everything else gets plain MessageMeta objects.

- Uses Google's official client and OAuth 2.0 (a refresh token, never your password).
- Fetches headers and labels only (format=metadata, no snippet): email bodies are never downloaded.
- Retries rate limits (429) and Google server errors (5xx) with backoff, then fails safely.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from . import config

HEADERS = ["From", "Reply-To", "Subject", "Date", "List-Unsubscribe", "Authentication-Results"]
# Only these fields come back from Google: no snippet, no body.
MESSAGE_FIELDS = "id,threadId,labelIds,internalDate,payload/headers"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class GmailError(Exception):
    """Gmail could not be reached or answered with an error. Safe to show (no secrets)."""


class GmailAuthError(GmailError):
    """Login failed: the refresh token expired, was revoked, or the client is wrong."""


@dataclass(frozen=True)
class MessageMeta:
    id: str
    thread_id: str
    labels: frozenset[str]
    headers: dict[str, str] = field(default_factory=dict)
    internal_date_ms: int = 0

    @property
    def unread(self) -> bool:
        return "UNREAD" in self.labels

    @property
    def sender(self) -> str:
        return self.headers.get("from", "")

    @property
    def subject(self) -> str:
        return self.headers.get("subject", "")


def _status(exc: Exception) -> int | None:
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _is_auth_failure(exc: Exception) -> bool:
    return type(exc).__name__ == "RefreshError" or _status(exc) == 401


def _is_retryable(exc: Exception) -> bool:
    if _status(exc) in RETRY_STATUSES:
        return True
    if type(exc).__name__ in ("ServerNotFoundError", "TransportError"):  # httplib2 / google-auth network errors
        return True
    return isinstance(exc, (ConnectionError, TimeoutError, OSError)) and _status(exc) is None


def build_client(settings: config.Settings) -> Any:
    """Make the real Gmail API client. Google libraries load only here."""
    if not settings.has_credentials:
        raise GmailAuthError(
            "Gmail is not set up: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET and GMAIL_REFRESH_TOKEN are needed."
        )
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=settings.refresh_token,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        token_uri=config.TOKEN_URI,
        scopes=config.SCOPES,
    )
    # The access token is fetched (and refreshed when it expires) by the library.
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


class GmailService:
    def __init__(self, client: Any, retries: int = 4, sleep: Callable[[float], None] = time.sleep):
        self._client = client
        self._retries = retries
        self._sleep = sleep
        self.api_calls = 0

    def _run(self, request: Any) -> dict:
        delay = 1.0
        for attempt in range(self._retries + 1):
            self.api_calls += 1
            try:
                return request.execute()
            except Exception as exc:  # Google raises several types; sort them here.
                if _is_auth_failure(exc):
                    raise GmailAuthError(
                        "Gmail login failed. The refresh token may have expired or been revoked: "
                        "run connect-gmail.bat again and update the GMAIL_REFRESH_TOKEN secret."
                    ) from None
                if _status(exc) == 403 and "insufficient" in str(exc).lower():
                    raise GmailAuthError(
                        "The Gmail login doesn't allow changes yet (read-only token). Run connect-gmail.bat "
                        "again, allow access, and update the GMAIL_REFRESH_TOKEN secret."
                    ) from None
                if _is_retryable(exc) and attempt < self._retries:
                    self._sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue
                status = _status(exc)
                raise GmailError(f"Gmail request failed ({status or type(exc).__name__}).") from None
        raise GmailError("Gmail request failed after retries.")  # not reached

    def profile(self) -> dict:
        return self._run(self._client.users().getProfile(userId="me"))

    def label_counts(self, label_id: str) -> dict:
        """Gmail's own totals for a label (e.g. INBOX), one cheap call."""
        data = self._run(self._client.users().labels().get(userId="me", id=label_id))
        return {"total": int(data.get("messagesTotal", 0)), "unread": int(data.get("messagesUnread", 0))}

    def list_message_ids(self, query: str, limit: int) -> Iterator[str]:
        """Page through matching message ids, stopping at `limit`."""
        token: str | None = None
        seen = 0
        while seen < limit:
            page = self._run(self._client.users().messages().list(
                userId="me", q=query, maxResults=min(100, limit - seen), pageToken=token,
                includeSpamTrash=False,
            ))
            for item in page.get("messages", []):
                yield item["id"]
                seen += 1
                if seen >= limit:
                    return
            token = page.get("nextPageToken")
            if not token:
                return

    def get_meta(self, message_id: str) -> MessageMeta:
        data = self._run(self._client.users().messages().get(
            userId="me", id=message_id, format="metadata", metadataHeaders=HEADERS, fields=MESSAGE_FIELDS,
        ))
        headers = {}
        for h in (data.get("payload") or {}).get("headers", []):
            name = str(h.get("name", "")).lower()
            if name and name not in headers:
                headers[name] = str(h.get("value", ""))
        return MessageMeta(
            id=data["id"],
            thread_id=data.get("threadId", ""),
            labels=frozenset(data.get("labelIds", [])),
            headers=headers,
            internal_date_ms=int(data.get("internalDate", 0) or 0),
        )

    def recent(self, query: str, limit: int) -> list[MessageMeta]:
        return [self.get_meta(mid) for mid in self.list_message_ids(query, limit)]

    # ---- Changes (only used when dry-run is off). Adding/removing labels only. ----

    def list_labels(self) -> dict[str, str]:
        """{label name: label id} for every label in the mailbox."""
        data = self._run(self._client.users().labels().list(userId="me"))
        return {lab["name"]: lab["id"] for lab in data.get("labels", [])}

    def create_label(self, name: str) -> str:
        body = {"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
        return self._run(self._client.users().labels().create(userId="me", body=body))["id"]

    def modify_labels(self, message_ids: list[str], add: list[str] | None = None,
                      remove: list[str] | None = None) -> None:
        """Add/remove label ids on up to 1000 messages per call (Gmail's limit)."""
        for i in range(0, len(message_ids), 1000):
            body = {"ids": message_ids[i:i + 1000]}
            if add:
                body["addLabelIds"] = add
            if remove:
                body["removeLabelIds"] = remove
            self._run(self._client.users().messages().batchModify(userId="me", body=body))

"""A stand-in for Google's Gmail client, so tests never touch a real mailbox.

It records every API method called, so tests can prove the scan only reads.
Use: client = FakeClient([...messages...]); client.users().messages().list(...)
"""
from __future__ import annotations


class FakeHttpError(Exception):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.resp = type("Resp", (), {"status": status})()


class RefreshError(Exception):
    """Same class name as google.auth.exceptions.RefreshError."""


class _Request:
    def __init__(self, client: "FakeClient", name: str, fn):
        self._client, self._name, self._fn = client, name, fn

    def execute(self):
        self._client.calls.append(self._name)
        if self._client.failures:
            raise self._client.failures.pop(0)
        return self._fn()


class _Messages:
    def __init__(self, client: "FakeClient"):
        self.c = client

    def list(self, userId, q, maxResults, pageToken=None, includeSpamTrash=False):
        start = int(pageToken or 0)
        chunk = self.c.data[start:start + min(self.c.page_size, maxResults)]
        nxt = start + len(chunk)

        def page():
            out = {"messages": [{"id": m["id"]} for m in chunk]}
            if chunk and nxt < len(self.c.data):
                out["nextPageToken"] = str(nxt)
            return out
        return _Request(self.c, "messages.list", page)

    def get(self, userId, id, format, metadataHeaders, fields):
        assert format == "metadata", "bodies must never be requested"
        assert "snippet" not in fields and "body" not in fields, "content must never be requested"
        return _Request(self.c, "messages.get", lambda: next(m for m in self.c.data if m["id"] == id))


class _Labels:
    def __init__(self, client: "FakeClient"):
        self.c = client

    def get(self, userId, id):
        total, unread = self.c.inbox
        return _Request(self.c, "labels.get", lambda: {"id": id, "messagesTotal": total, "messagesUnread": unread})


class _Users:
    def __init__(self, client: "FakeClient"):
        self.c = client

    def messages(self):
        return _Messages(self.c)

    def labels(self):
        return _Labels(self.c)

    def getProfile(self, userId):
        return _Request(self.c, "getProfile", lambda: {"emailAddress": "me@example.com"})


class FakeClient:
    def __init__(self, data: list[dict], page_size: int = 2, inbox=(10, 3)):
        self.data = data
        self.page_size = page_size
        self.inbox = inbox
        self.calls: list[str] = []
        self.failures: list[Exception] = []  # raised in order before the next success

    def users(self):
        return _Users(self)


def msg(i: int, labels=("INBOX",), unsubscribe=False, sender="a@example.com", subject="Hello"):
    headers = [{"name": "From", "value": sender}, {"name": "Subject", "value": subject}]
    if unsubscribe:
        headers.append({"name": "List-Unsubscribe", "value": "<mailto:u@example.com>"})
    return {"id": f"m{i}", "threadId": f"t{i}", "labelIds": list(labels),
            "internalDate": "1700000000000", "payload": {"headers": headers}}

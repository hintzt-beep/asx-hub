"""Read-only scan: counts only. Nothing in Gmail is changed."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .gmail_service import GmailService, MessageMeta

# Gmail's own tabs and flags, shown with friendly names.
GMAIL_LABELS = {
    "CATEGORY_PERSONAL": "Primary",
    "CATEGORY_SOCIAL": "Social",
    "CATEGORY_PROMOTIONS": "Promotions",
    "CATEGORY_UPDATES": "Updates",
    "CATEGORY_FORUMS": "Forums",
    "IMPORTANT": "Marked important",
    "STARRED": "Starred",
}


@dataclass
class ScanReport:
    query: str
    scanned: int
    unread: int
    inbox_total: int
    inbox_unread: int
    by_gmail_label: dict[str, int]
    with_unsubscribe: int
    api_calls: int
    finished_at: str
    samples: list[MessageMeta] = field(default_factory=list)

    def counts_text(self) -> str:
        """Safe for public logs: numbers only, no senders or subjects."""
        lines = [
            f"Inbox: {self.inbox_total} messages, {self.inbox_unread} unread",
            f"Scanned ({self.query}): {self.scanned} messages, {self.unread} unread",
        ]
        for name, n in sorted(self.by_gmail_label.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {name}: {n}")
        lines.append(f"  With an unsubscribe link: {self.with_unsubscribe}")
        lines.append(f"Gmail API calls: {self.api_calls}. Finished {self.finished_at}. Read-only: nothing changed.")
        return "\n".join(lines)


def run_scan(service: GmailService, query: str, limit: int, keep_samples: int = 0) -> ScanReport:
    inbox = service.label_counts("INBOX")
    messages = service.recent(query, limit)
    labels = Counter()
    for m in messages:
        for gid, name in GMAIL_LABELS.items():
            if gid in m.labels:
                labels[name] += 1
    return ScanReport(
        query=query,
        scanned=len(messages),
        unread=sum(1 for m in messages if m.unread),
        inbox_total=inbox["total"],
        inbox_unread=inbox["unread"],
        by_gmail_label=dict(labels),
        with_unsubscribe=sum(1 for m in messages if "list-unsubscribe" in m.headers),
        api_calls=service.api_calls,
        finished_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        samples=messages[:keep_samples],
    )

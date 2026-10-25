"""Dry-run report: what the agent WOULD do. Nothing in Gmail is changed."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import rules
from .classifier import Classification, classify
from .gmail_service import GmailService, MessageMeta

LABEL_PREFIX = "Agent/"


@dataclass(frozen=True)
class ProposedAction:
    message_id: str
    kind: str          # "label" or "spam" (more kinds come later)
    value: str         # label name, or "" for spam
    reason: str


def propose(c: Classification) -> list[ProposedAction]:
    """Actions the agent would take for one email. Dry-run only in this increment."""
    actions: list[ProposedAction] = []
    if c.spam_level == "high":
        actions.append(ProposedAction(c.message_id, "spam", "", "; ".join(c.reasons)))
        return actions  # spam gets no other labels
    if c.spam_level == "review":
        actions.append(ProposedAction(c.message_id, "label", LABEL_PREFIX + "Review", "; ".join(c.reasons)))
    elif c.category not in ("Other / uncertain",):
        actions.append(ProposedAction(c.message_id, "label", LABEL_PREFIX + c.category, ", ".join(c.reasons)))
    if c.urgent:
        actions.append(ProposedAction(c.message_id, "label", LABEL_PREFIX + "Needs action", "urgent subject"))
    if c.needs_reply:
        actions.append(ProposedAction(c.message_id, "label", LABEL_PREFIX + "Needs reply", "a person, may want a reply"))
    return actions


@dataclass
class DryRunReport:
    scanned: int
    by_category: dict[str, int]
    urgent: int
    needs_reply: int
    spam_high: int
    spam_review: int
    protected: int
    actions: Counter
    api_calls: int
    finished_at: str
    rows: list[tuple[MessageMeta, Classification, list[ProposedAction]]] = field(default_factory=list)

    def counts_text(self) -> str:
        """Numbers only: safe for public GitHub logs."""
        lines = [f"DRY RUN: nothing in Gmail was changed. Scanned {self.scanned} emails."]
        for cat in rules.CATEGORIES:
            if self.by_category.get(cat):
                lines.append(f"  {cat}: {self.by_category[cat]}")
        lines += [
            f"Needs action: {self.urgent}   Needs reply: {self.needs_reply}   Protected senders: {self.protected}",
            f"Likely spam (would move to Spam): {self.spam_high}   Suspicious (for your review): {self.spam_review}",
            "Would do: " + (", ".join(f"{n} x {k}" for k, n in sorted(self.actions.items())) or "nothing"),
            f"Gmail API calls: {self.api_calls}. Finished {self.finished_at}.",
        ]
        return "\n".join(lines)


def build_report(messages: list[MessageMeta], api_calls: int = 0, keep_rows: int = 0) -> DryRunReport:
    rows = []
    for m in messages:
        c = classify(m)
        rows.append((m, c, propose(c)))
    actions = Counter()
    for _, _, acts in rows:
        for a in acts:
            actions["move to Spam" if a.kind == "spam" else f"label {a.value}"] += 1
    cls = [c for _, c, _ in rows]
    return DryRunReport(
        scanned=len(rows),
        by_category=dict(Counter(c.category for c in cls)),
        urgent=sum(c.urgent for c in cls),
        needs_reply=sum(c.needs_reply for c in cls),
        spam_high=sum(c.spam_level == "high" for c in cls),
        spam_review=sum(c.spam_level == "review" for c in cls),
        protected=sum(c.protected for c in cls),
        actions=actions,
        api_calls=api_calls,
        finished_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        rows=rows[:keep_rows],
    )


def run_dry_run(service: GmailService, query: str, limit: int, keep_rows: int = 0) -> DryRunReport:
    messages = service.recent(query, limit)
    return build_report(messages, service.api_calls, keep_rows)

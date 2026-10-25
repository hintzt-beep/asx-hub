"""Applies the agent's label proposals to Gmail. Labels only in this increment.

Safety rules:
- Dry-run unless GMAIL_DRY_RUN=0 is set explicitly: then it only reports.
- Only ADDS labels under "Agent/". Never removes your labels, never archives, never deletes.
- Spam proposals are logged as "proposed" but not executed (Spam moves come in a later step).
- Idempotent: a label already on an email (or already applied by the agent) is skipped.
- The activity log must load and save first; if it can't, Gmail is not touched.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .audit import AuditLog
from .classifier import classify
from .gmail_service import GmailError, GmailService, MessageMeta
from .report import LABEL_PREFIX, propose

PARENT_LABEL = LABEL_PREFIX.rstrip("/")


@dataclass
class ApplyResult:
    run_id: str
    dry_run: bool
    planned: dict[str, int] = field(default_factory=dict)      # label -> emails to label
    skipped_existing: int = 0
    spam_proposed: int = 0
    labels_created: list[str] = field(default_factory=list)
    applied: int = 0

    def text(self) -> str:
        head = "DRY RUN: nothing in Gmail was changed." if self.dry_run else f"APPLIED (run {self.run_id})."
        lines = [head]
        for name, n in sorted(self.planned.items()):
            lines.append(f"  {'would label' if self.dry_run else 'labelled'} {n} x {name}")
        if self.labels_created:
            lines.append(f"  new labels created: {len(self.labels_created)}")
        lines.append(f"  already labelled, skipped: {self.skipped_existing}")
        lines.append(f"  likely spam (not moved yet, logged for later): {self.spam_proposed}")
        if not self.dry_run:
            lines.append(f"  total labels added: {self.applied}. Undo with: python -m gmail_agent.cli undo")
        return "\n".join(lines)


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def apply_labels(service: GmailService, messages: list[MessageMeta], audit: AuditLog,
                 dry_run: bool, run_id: str | None = None) -> ApplyResult:
    run_id = run_id or new_run_id()
    result = ApplyResult(run_id=run_id, dry_run=dry_run)
    existing = service.list_labels()                       # read-only call
    done = audit.applied_keys()

    wanted: dict[str, list[tuple[str, str]]] = defaultdict(list)  # label name -> [(message id, reason)]
    spam: list[tuple[str, str]] = []
    for m in messages:
        for a in propose(classify(m)):
            if a.kind == "spam":
                spam.append((m.id, a.reason))
                continue
            label_id = existing.get(a.value)
            if (label_id and label_id in m.labels) or (m.id, a.value) in done:
                result.skipped_existing += 1
                continue
            wanted[a.value].append((m.id, a.reason))
    result.planned = {name: len(items) for name, items in wanted.items()}
    result.spam_proposed = len(spam)
    if dry_run or (not wanted and not spam):
        return result

    # 1. Log what we're about to do. If this fails, stop before touching Gmail.
    for m_id, reason in spam:
        audit.add(run_id, m_id, "spam", "", "proposed", reason)
    for name, items in wanted.items():
        for m_id, reason in items:
            audit.add(run_id, m_id, "label", name, "proposed", reason)
    audit.save()

    # 2. Create any missing labels (parent "Agent" first so they nest in Gmail).
    for name in [PARENT_LABEL] + sorted(wanted):
        if name not in existing:
            existing[name] = service.create_label(name)
            result.labels_created.append(name)
            audit.add(run_id, "", "create_label", name, "applied")

    # 3. Apply, one batch call per label. Log each outcome.
    try:
        for name, items in sorted(wanted.items()):
            ids = [m_id for m_id, _ in items]
            service.modify_labels(ids, add=[existing[name]])
            for m_id, reason in items:
                audit.add(run_id, m_id, "label", name, "applied", reason)
            result.applied += len(ids)
    except GmailError:
        audit.add(run_id, "", "run", "", "failed", "Gmail error part-way; see run log")
        audit.save()
        raise
    audit.save()
    return result


def undo_run(service: GmailService, audit: AuditLog, run_id: str | None = None,
             dry_run: bool = True) -> tuple[str, int]:
    """Remove the labels a run added. Defaults to the most recent run. Labels stay (empty)."""
    runs = audit.runs()
    if not runs:
        return "", 0
    run_id = run_id or runs[-1]
    live = audit.applied_keys()
    by_label: dict[str, list[str]] = defaultdict(list)
    for e in audit.entries:
        if e.get("run") == run_id and e.get("kind") == "label" and e.get("status") == "applied" \
                and (e["message_id"], e["value"]) in live:
            by_label[e["value"]].append(e["message_id"])
    count = sum(len(v) for v in by_label.values())
    if dry_run or not count:
        return run_id, count
    ids_by_name = service.list_labels()
    undo_id = "undo-" + new_run_id()
    for name, ids in by_label.items():
        if name in ids_by_name:
            service.modify_labels(ids, remove=[ids_by_name[name]])
        for m_id in ids:
            audit.add(undo_id, m_id, "label", name, "undone", f"undo of run {run_id}")
    audit.save()
    return run_id, count

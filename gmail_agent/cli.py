"""Command line for the Gmail agent.

  python -m gmail_agent.cli scan      counts only (read-only)
  python -m gmail_agent.cli report    dry run: how each email would be sorted (read-only)
  python -m gmail_agent.cli apply     add Agent/ labels. Dry run unless GMAIL_DRY_RUN=0
  python -m gmail_agent.cli undo      remove the labels added by the last apply (GMAIL_DRY_RUN=0 to do it)

On GitHub Actions (public logs) only counts are printed. On your own PC `--samples N`
also shows senders and subjects.
"""
from __future__ import annotations

import argparse
import os
import sys

from . import config
from .actions import apply_labels, undo_run
from .audit import AuditError, AuditLog, MemoryStore, SupabaseStore
from .gmail_service import GmailError, GmailService, build_client
from .report import run_dry_run
from .scan import run_scan


def _in_public_ci() -> bool:
    return os.environ.get("GITHUB_ACTIONS", "").lower() == "true"


def _audit_store():
    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"):
        return SupabaseStore()
    return None


def main(argv: list[str] | None = None, store=None) -> int:
    parser = argparse.ArgumentParser(prog="gmail_agent")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("scan", "read-only scan, prints counts"),
                       ("report", "dry run: sort emails and show what would happen")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--samples", type=int, default=0, help="show senders/subjects (your PC only)")
    sub.add_parser("apply", help="add Agent/ labels (dry run unless GMAIL_DRY_RUN=0)")
    undo = sub.add_parser("undo", help="remove labels added by an apply run (dry run unless GMAIL_DRY_RUN=0)")
    undo.add_argument("--run", default=None, help="run id to undo (default: the latest)")
    args = parser.parse_args(argv)

    settings = config.load()
    if not settings.enabled:
        print("Gmail agent is switched off (GMAIL_AGENT_ENABLED=0). Nothing done.")
        return 0

    samples = getattr(args, "samples", 0)
    if samples and _in_public_ci():
        print("Samples are never printed on GitHub Actions (the logs are public). Showing counts only.")
        samples = 0

    if args.command in ("apply", "undo"):
        return _changes(args, settings, store)

    try:
        service = GmailService(build_client(settings))
        if args.command == "report":
            dry = run_dry_run(service, settings.query, settings.max_messages, keep_rows=samples)
        else:
            report = run_scan(service, settings.query, settings.max_messages, keep_samples=samples)
    except GmailError as exc:
        # Fail safely: report the problem, change nothing, exit non-zero so the run shows red.
        print(f"Gmail scan stopped safely: {exc}")
        return 1

    if args.command == "report":
        print(dry.counts_text())
        for m, c, acts in dry.rows:
            tags = [t for t, on in (("urgent", c.urgent), ("reply", c.needs_reply),
                                    ("protected", c.protected)) if on]
            spam = f" spam={c.spam_score}" if c.spam_score else ""
            print(f"  {c.category[:22]:22} {','.join(tags):18}{spam:10} {m.sender[:40]:40} {m.subject[:60]}")
            for a in acts:
                print(f"      would {a.kind} {a.value}  ({a.reason})")
        return 0

    print(report.counts_text())
    for m in report.samples:
        flag = "unread" if m.unread else "read  "
        print(f"  [{flag}] {m.sender[:50]:50}  {m.subject[:70]}")
    return 0


def _changes(args, settings: config.Settings, store) -> int:
    store = store or _audit_store()
    if store is None:
        if not settings.dry_run:
            print("Stopped safely: changes need the activity log (SUPABASE_URL and SUPABASE_KEY). Nothing changed.")
            return 1
        store = MemoryStore()  # dry run on a PC: nothing to log
    try:
        audit = AuditLog(store).load()
        service = GmailService(build_client(settings))
        if args.command == "apply":
            messages = service.recent(settings.query, settings.max_messages)
            result = apply_labels(service, messages, audit, dry_run=settings.dry_run)
            print(result.text())
        else:
            run_id, n = undo_run(service, audit, args.run, dry_run=settings.dry_run)
            if not run_id:
                print("Nothing to undo: no labels have been applied yet.")
            elif settings.dry_run:
                print(f"DRY RUN: undo of run {run_id} would remove {n} labels. Set GMAIL_DRY_RUN=0 to do it.")
            else:
                print(f"Undone: removed {n} labels added by run {run_id}.")
    except (GmailError, AuditError) as exc:
        print(f"Stopped safely: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

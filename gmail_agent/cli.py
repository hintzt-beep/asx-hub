"""Command line: `python -m gmail_agent.cli scan`.

On GitHub Actions (public logs) it prints counts only. On your own PC you can add
`--samples 10` to also see sender and subject of the first few messages.
"""
from __future__ import annotations

import argparse
import os
import sys

from . import config
from .gmail_service import GmailError, GmailService, build_client
from .report import run_dry_run
from .scan import run_scan


def _in_public_ci() -> bool:
    return os.environ.get("GITHUB_ACTIONS", "").lower() == "true"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gmail_agent")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="read-only scan, prints counts")
    scan.add_argument("--samples", type=int, default=0, help="show sender/subject of N messages (your PC only)")
    rep = sub.add_parser("report", help="dry run: sort emails and show what would happen (changes nothing)")
    rep.add_argument("--samples", type=int, default=0, help="show each email's category (your PC only)")
    args = parser.parse_args(argv)

    settings = config.load()
    if not settings.enabled:
        print("Gmail agent is switched off (GMAIL_AGENT_ENABLED=0). Nothing done.")
        return 0

    samples = args.samples
    if samples and _in_public_ci():
        print("Samples are never printed on GitHub Actions (the logs are public). Showing counts only.")
        samples = 0

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


if __name__ == "__main__":
    sys.exit(main())

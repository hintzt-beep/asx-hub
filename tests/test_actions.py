"""Increment 3 tests: label actions, dry-run safety, duplicates, audit log, undo.

Run:  python -m unittest discover -s tests -t .
"""
from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from gmail_agent import cli
from gmail_agent.actions import apply_labels, undo_run
from gmail_agent.audit import MAX_ENTRIES, AuditError, AuditLog, MemoryStore
from gmail_agent.gmail_service import GmailAuthError, GmailError, GmailService
from tests.fake_gmail import FakeClient, FakeHttpError, msg

WRITE_CALLS = {"labels.create", "messages.batchModify"}
FAIL_AUTH = "mx.google.com; dkim=fail; spf=fail; dmarc=fail"


def mailbox():
    data = [msg(1, sender="AGL <bills@agl.com.au>", subject="Your bill is due tomorrow"),
            msg(2, sender="Jess <jess@gmail.com>", subject="Lunch?"),
            msg(3, sender="Someone <a@unknown.biz>", subject="Hi")]
    phish = msg(4, sender="PayPal <a@paypa1.xyz>", subject="Account suspended")
    phish["payload"]["headers"].append({"name": "Authentication-Results", "value": FAIL_AUTH})
    data.append(phish)
    return FakeClient(data, page_size=10)


def run(client, audit, dry_run):
    svc = GmailService(client, sleep=lambda s: None)
    return apply_labels(svc, svc.recent("q", 50), audit, dry_run=dry_run, run_id="r1")


def label_names(client, msg_id):
    ids = next(m for m in client.data if m["id"] == msg_id)["labelIds"]
    by_id = {v: k for k, v in client.labels.items()}
    return {by_id.get(i, i) for i in ids}


class DryRunTests(unittest.TestCase):
    def test_dry_run_makes_no_changes(self):
        client, audit = mailbox(), AuditLog(MemoryStore())
        result = run(client, audit, dry_run=True)
        self.assertFalse(WRITE_CALLS & set(client.calls), client.calls)
        self.assertEqual(audit.entries, [])
        self.assertEqual(result.planned["Agent/Bills and payments"], 1)
        self.assertIn("DRY RUN", result.text())

    def test_dry_run_is_the_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            from gmail_agent import config
            self.assertTrue(config.load().dry_run)


class ApplyTests(unittest.TestCase):
    def test_apply_adds_labels(self):
        client, audit = mailbox(), AuditLog(MemoryStore())
        result = run(client, audit, dry_run=False)
        self.assertIn("Agent/Bills and payments", label_names(client, "m1"))
        self.assertIn("Agent/Needs action", label_names(client, "m1"))
        self.assertIn("Agent/Personal", label_names(client, "m2"))
        self.assertIn("Agent", client.labels)  # parent created so labels nest
        self.assertGreater(result.applied, 0)

    def test_never_removes_or_moves(self):
        client, audit = mailbox(), AuditLog(MemoryStore())
        run(client, audit, dry_run=False)
        for m in client.data:
            self.assertIn("INBOX", m["labelIds"])  # nothing archived
            self.assertNotIn("SPAM", m["labelIds"])
            self.assertNotIn("TRASH", m["labelIds"])

    def test_spam_is_logged_not_executed(self):
        client, audit = mailbox(), AuditLog(MemoryStore())
        result = run(client, audit, dry_run=False)
        self.assertEqual(result.spam_proposed, 1)
        self.assertEqual(label_names(client, "m4"), {"INBOX"})
        spam = [e for e in audit.entries if e["kind"] == "spam"]
        self.assertEqual([e["status"] for e in spam], ["proposed"])

    def test_uncertain_email_untouched(self):
        client, audit = mailbox(), AuditLog(MemoryStore())
        run(client, audit, dry_run=False)
        self.assertEqual(label_names(client, "m3"), {"INBOX"})

    def test_second_run_adds_nothing(self):
        client, audit = mailbox(), AuditLog(MemoryStore())
        run(client, audit, dry_run=False)
        calls_before = len(client.calls)
        second = run(client, audit, dry_run=False)
        self.assertEqual(second.applied, 0)
        self.assertGreater(second.skipped_existing, 0)
        self.assertFalse(WRITE_CALLS & set(client.calls[calls_before:]))

    def test_existing_labels_reused(self):
        client = mailbox()
        client.labels["Agent"] = "L_a"
        client.labels["Agent/Personal"] = "L_p"
        run(client, AuditLog(MemoryStore()), dry_run=False)  # fake raises on duplicate create
        self.assertIn("Agent/Personal", label_names(client, "m2"))

    def test_one_batch_call_per_label(self):
        client = FakeClient([msg(i, sender="AGL <b@agl.com.au>", subject="Bill") for i in range(25)], page_size=50)
        run(client, AuditLog(MemoryStore()), dry_run=False)
        self.assertEqual(client.calls.count("messages.batchModify"), 1)

    def test_user_labels_untouched(self):
        client = mailbox()
        client.data[1]["labelIds"].append("Label_0")  # user's own "Receipts" label
        run(client, AuditLog(MemoryStore()), dry_run=False)
        self.assertIn("Receipts", label_names(client, "m2"))


class AuditTests(unittest.TestCase):
    def test_every_action_logged_without_private_data(self):
        client, audit = mailbox(), AuditLog(MemoryStore())
        run(client, audit, dry_run=False)
        statuses = {(e["message_id"], e["value"], e["status"]) for e in audit.entries}
        self.assertIn(("m1", "Agent/Bills and payments", "proposed"), statuses)
        self.assertIn(("m1", "Agent/Bills and payments", "applied"), statuses)
        blob = str(audit.entries).lower()
        self.assertNotIn("jess", blob)
        self.assertNotIn("lunch", blob)

    def test_log_failure_stops_before_gmail_changes(self):
        class BrokenStore(MemoryStore):
            def put(self, *a):
                raise ConnectionError("supabase down")
        client = mailbox()
        with self.assertRaises(AuditError):
            run(client, AuditLog(BrokenStore()), dry_run=False)
        self.assertFalse(WRITE_CALLS & set(client.calls))

    def test_unreadable_log_fails_safely(self):
        class BrokenStore(MemoryStore):
            def get(self, *a):
                raise ConnectionError("down")
        with self.assertRaises(AuditError):
            AuditLog(BrokenStore()).load()

    def test_log_is_capped(self):
        audit = AuditLog(MemoryStore())
        for i in range(MAX_ENTRIES + 50):
            audit.add("r", f"m{i}", "label", "x", "applied")
        audit.save()
        self.assertEqual(len(AuditLog(audit.store).load().entries), MAX_ENTRIES)

    def test_gmail_error_midway_is_logged(self):
        client, audit = mailbox(), AuditLog(MemoryStore())
        svc = GmailService(client, retries=0, sleep=lambda s: None)
        msgs = svc.recent("q", 50)
        client.fail_calls = {"messages.batchModify"}
        with self.assertRaises(GmailError):
            apply_labels(svc, msgs, audit, dry_run=False, run_id="r1")
        self.assertIn("failed", [e["status"] for e in audit.entries])

    def test_read_only_token_gives_clear_message(self):
        client = mailbox()
        err = FakeHttpError(403)
        err.args = ("Request had insufficient authentication scopes.",)
        client.failures = [err]
        with self.assertRaises(GmailAuthError) as ctx:
            GmailService(client, sleep=lambda s: None).list_labels()
        self.assertIn("connect-gmail.bat", str(ctx.exception))


class UndoTests(unittest.TestCase):
    def test_undo_removes_only_agent_labels(self):
        client, audit = mailbox(), AuditLog(MemoryStore())
        client.data[1]["labelIds"].append("Label_0")
        run(client, audit, dry_run=False)
        svc = GmailService(client, sleep=lambda s: None)
        run_id, n = undo_run(svc, audit, dry_run=False)
        self.assertEqual(run_id, "r1")
        self.assertGreater(n, 0)
        self.assertEqual(label_names(client, "m1"), {"INBOX"})
        self.assertEqual(label_names(client, "m2"), {"INBOX", "Receipts"})

    def test_undo_dry_run_changes_nothing(self):
        client, audit = mailbox(), AuditLog(MemoryStore())
        run(client, audit, dry_run=False)
        before = len(client.calls)
        _, n = undo_run(GmailService(client), audit, dry_run=True)
        self.assertGreater(n, 0)
        self.assertFalse(WRITE_CALLS & set(client.calls[before:]))

    def test_undo_twice_does_nothing_more(self):
        client, audit = mailbox(), AuditLog(MemoryStore())
        run(client, audit, dry_run=False)
        svc = GmailService(client)
        undo_run(svc, audit, dry_run=False)
        _, n = undo_run(svc, audit, "r1", dry_run=False)
        self.assertEqual(n, 0)

    def test_reapply_after_undo(self):
        client, audit = mailbox(), AuditLog(MemoryStore())
        run(client, audit, dry_run=False)
        undo_run(GmailService(client), audit, dry_run=False)
        again = run(client, audit, dry_run=False)
        self.assertGreater(again.applied, 0)

    def test_nothing_to_undo(self):
        self.assertEqual(undo_run(GmailService(mailbox()), AuditLog(MemoryStore())), ("", 0))


class CliTests(unittest.TestCase):
    def call(self, env, argv, client, store):
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), redirect_stdout(out), \
                mock.patch.object(cli, "build_client", return_value=client):
            code = cli.main(argv, store=store)
        return code, out.getvalue()

    def test_apply_defaults_to_dry_run(self):
        client = mailbox()
        code, out = self.call({}, ["apply"], client, MemoryStore())
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN", out)
        self.assertFalse(WRITE_CALLS & set(client.calls))

    def test_apply_for_real(self):
        client, store = mailbox(), MemoryStore()
        code, out = self.call({"GMAIL_DRY_RUN": "0"}, ["apply"], client, store)
        self.assertEqual(code, 0)
        self.assertIn("APPLIED", out)
        self.assertIn("messages.batchModify", client.calls)

    def test_real_apply_refuses_without_log(self):
        client = mailbox()
        code, out = self.call({"GMAIL_DRY_RUN": "0"}, ["apply"], client, None)
        self.assertEqual(code, 1)
        self.assertIn("Stopped safely", out)
        self.assertFalse(WRITE_CALLS & set(client.calls))

    def test_switched_off_does_nothing(self):
        client = mailbox()
        code, out = self.call({"GMAIL_AGENT_ENABLED": "0", "GMAIL_DRY_RUN": "0"}, ["apply"], client, MemoryStore())
        self.assertIn("switched off", out)
        self.assertEqual(client.calls, [])

    def test_apply_output_is_private(self):
        client = mailbox()
        _, out = self.call({"GITHUB_ACTIONS": "true", "GMAIL_DRY_RUN": "0"}, ["apply"], client, MemoryStore())
        self.assertNotIn("jess", out.lower())
        self.assertNotIn("agl.com.au", out)

    def test_undo_command(self):
        client, store = mailbox(), MemoryStore()
        self.call({"GMAIL_DRY_RUN": "0"}, ["apply"], client, store)
        _, out = self.call({"GMAIL_DRY_RUN": "0"}, ["undo"], client, store)
        self.assertIn("Undone", out)
        self.assertEqual(label_names(client, "m1"), {"INBOX"})


if __name__ == "__main__":
    unittest.main()

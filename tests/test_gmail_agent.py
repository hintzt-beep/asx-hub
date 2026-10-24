"""Increment 1 tests: read-only scan, pagination, error handling, safe logging.

Run:  python -m unittest discover -s tests -v     (or: pytest tests)
"""
from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from gmail_agent import cli, config
from gmail_agent.gmail_service import GmailAuthError, GmailError, GmailService
from gmail_agent.scan import run_scan
from tests.fake_gmail import FakeClient, FakeHttpError, RefreshError, msg

READ_ONLY_CALLS = {"messages.list", "messages.get", "labels.get", "getProfile"}


def service(client: FakeClient) -> GmailService:
    return GmailService(client, retries=3, sleep=lambda s: None)


class ScanTests(unittest.TestCase):
    def test_counts(self):
        data = [msg(1, ("INBOX", "UNREAD", "CATEGORY_PROMOTIONS"), unsubscribe=True),
                msg(2, ("INBOX", "CATEGORY_PERSONAL")),
                msg(3, ("INBOX", "UNREAD", "CATEGORY_PROMOTIONS", "IMPORTANT"))]
        report = run_scan(service(FakeClient(data, inbox=(120, 7))), "newer_than:1d", 50)
        self.assertEqual(report.scanned, 3)
        self.assertEqual(report.unread, 2)
        self.assertEqual((report.inbox_total, report.inbox_unread), (120, 7))
        self.assertEqual(report.by_gmail_label["Promotions"], 2)
        self.assertEqual(report.by_gmail_label["Primary"], 1)
        self.assertEqual(report.with_unsubscribe, 1)

    def test_scan_only_reads(self):
        client = FakeClient([msg(i) for i in range(5)])
        run_scan(service(client), "q", 50)
        self.assertTrue(set(client.calls) <= READ_ONLY_CALLS, client.calls)

    def test_pagination_follows_pages(self):
        client = FakeClient([msg(i) for i in range(7)], page_size=2)
        report = run_scan(service(client), "q", 50)
        self.assertEqual(report.scanned, 7)
        self.assertEqual(client.calls.count("messages.list"), 4)

    def test_limit_stops_early(self):
        client = FakeClient([msg(i) for i in range(10)], page_size=3)
        report = run_scan(service(client), "q", 4)
        self.assertEqual(report.scanned, 4)
        self.assertEqual(client.calls.count("messages.get"), 4)

    def test_empty_mailbox(self):
        report = run_scan(service(FakeClient([])), "q", 50)
        self.assertEqual(report.scanned, 0)

    def test_counts_text_has_no_senders_or_subjects(self):
        data = [msg(1, sender="secret.person@bank.com", subject="Your PIN is ready")]
        text = run_scan(service(FakeClient(data)), "q", 50).counts_text()
        self.assertNotIn("secret.person", text)
        self.assertNotIn("PIN", text)


class ErrorTests(unittest.TestCase):
    def test_rate_limit_is_retried(self):
        client = FakeClient([msg(1)])
        client.failures = [FakeHttpError(429), FakeHttpError(503)]
        report = run_scan(service(client), "q", 50)
        self.assertEqual(report.scanned, 1)

    def test_gives_up_after_retries(self):
        client = FakeClient([msg(1)])
        client.failures = [FakeHttpError(500)] * 10
        with self.assertRaises(GmailError):
            run_scan(service(client), "q", 50)

    def test_expired_token_is_auth_error(self):
        client = FakeClient([msg(1)])
        client.failures = [RefreshError("invalid_grant")]
        with self.assertRaises(GmailAuthError):
            run_scan(service(client), "q", 50)

    def test_forbidden_is_not_retried(self):
        client = FakeClient([msg(1)])
        client.failures = [FakeHttpError(403), FakeHttpError(403)]
        with self.assertRaises(GmailError):
            run_scan(service(client), "q", 50)
        self.assertEqual(len(client.calls), 1)

    def test_network_error_retried(self):
        client = FakeClient([msg(1)])
        client.failures = [ConnectionError("down")]
        self.assertEqual(run_scan(service(client), "q", 50).scanned, 1)

    def test_error_messages_hold_no_secrets(self):
        client = FakeClient([msg(1)])
        client.failures = [RefreshError("token=abc123SECRET")]
        try:
            run_scan(service(client), "q", 50)
        except GmailAuthError as exc:
            self.assertNotIn("abc123SECRET", str(exc))
            self.assertIsNone(exc.__cause__)


class ConfigTests(unittest.TestCase):
    def test_defaults_are_safe(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            s = config.load()
        self.assertTrue(s.dry_run)
        self.assertFalse(s.has_credentials)
        self.assertEqual(config.SCOPES_READONLY, ["https://www.googleapis.com/auth/gmail.readonly"])

    def test_authorize_asks_for_the_same_scope(self):
        from gmail_agent import authorize
        self.assertEqual(authorize.SCOPES, config.SCOPES_READONLY)

    def test_limits_are_clamped(self):
        with mock.patch.dict(os.environ, {"GMAIL_MAX_MESSAGES": "99999"}, clear=True):
            self.assertEqual(config.load().max_messages, 500)
        with mock.patch.dict(os.environ, {"GMAIL_MAX_MESSAGES": "lots"}, clear=True):
            self.assertEqual(config.load().max_messages, 200)


try:
    import googleapiclient  # noqa: F401
    HAVE_GOOGLE = True
except ImportError:
    HAVE_GOOGLE = False


@unittest.skipUnless(HAVE_GOOGLE, "Google libraries not installed (they are on GitHub Actions)")
class RealClientTests(unittest.TestCase):
    def test_real_client_builds_offline_with_read_only_scope(self):
        from gmail_agent.gmail_service import build_client
        s = config.Settings(enabled=True, dry_run=True, query="q", max_messages=1,
                            client_id="id", client_secret="secret", refresh_token="token")
        client = build_client(s)  # no network: Gmail's API description ships with the library
        self.assertTrue(hasattr(client.users().messages(), "list"))
        self.assertEqual(client._http.credentials.scopes, config.SCOPES_READONLY)


class CliTests(unittest.TestCase):
    def _run(self, env, argv, client=None):
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), redirect_stdout(out), \
                mock.patch.object(cli, "build_client", return_value=client or FakeClient([msg(1)])):
            code = cli.main(argv)
        return code, out.getvalue()

    def test_switched_off(self):
        code, out = self._run({"GMAIL_AGENT_ENABLED": "0"}, ["scan"])
        self.assertEqual(code, 0)
        self.assertIn("switched off", out)

    def test_samples_never_printed_on_github_actions(self):
        client = FakeClient([msg(1, sender="private@person.com", subject="Private matter")])
        code, out = self._run({"GITHUB_ACTIONS": "true"}, ["scan", "--samples", "5"], client)
        self.assertEqual(code, 0)
        self.assertNotIn("private@person.com", out)
        self.assertNotIn("Private matter", out)

    def test_samples_shown_locally(self):
        client = FakeClient([msg(1, sender="friend@example.com", subject="Lunch")])
        _, out = self._run({}, ["scan", "--samples", "5"], client)
        self.assertIn("friend@example.com", out)

    def test_missing_credentials_fails_safely(self):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), redirect_stdout(out):
            code = cli.main(["scan"])
        self.assertEqual(code, 1)
        self.assertIn("stopped safely", out.getvalue())


if __name__ == "__main__":
    unittest.main()

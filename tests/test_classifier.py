"""Increment 2 tests: sorting rules, spam confidence thresholds, protected senders, dry-run safety.

Run:  python -m unittest discover -s tests -t .
"""
from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from gmail_agent import cli, rules
from gmail_agent.classifier import auth_results, classify, sender_parts
from gmail_agent.gmail_service import MessageMeta
from gmail_agent.report import build_report, propose
from tests.fake_gmail import FakeClient, msg

PASS = "mx.google.com; dkim=pass; spf=pass; dmarc=pass"
FAIL = "mx.google.com; dkim=fail; spf=fail; dmarc=fail"


def m(sender, subject="Hello", labels=("INBOX",), auth=PASS, unsubscribe=False, reply_to=None, i="1"):
    headers = {"from": sender, "subject": subject, "authentication-results": auth}
    if unsubscribe:
        headers["list-unsubscribe"] = "<mailto:u@x.com>"
    if reply_to:
        headers["reply-to"] = reply_to
    return MessageMeta(id=i, thread_id="t" + i, labels=frozenset(labels), headers=headers)


class CategoryTests(unittest.TestCase):
    def cat(self, *a, **k):
        return classify(m(*a, **k)).category

    def test_bank(self):
        self.assertEqual(self.cat("CommBank <notify@notify.commbank.com.au>", "Your statement is ready"),
                         "Finance and banking")

    def test_bill(self):
        self.assertEqual(self.cat("AGL <bills@agl.com.au>", "Your bill"), "Bills and payments")

    def test_shopping(self):
        self.assertEqual(self.cat("Amazon <shipment-tracking@amazon.com.au>", "Your order has shipped"),
                         "Shopping and orders")

    def test_travel(self):
        self.assertEqual(self.cat("Qantas <no-reply@qantas.com.au>", "Your booking"), "Travel and bookings")

    def test_personal(self):
        self.assertEqual(self.cat("Jess Smith <jess.smith@gmail.com>", "Saturday?"), "Personal")

    def test_newsletter(self):
        self.assertEqual(self.cat("Shop <deals@someshop.com>", "50% off", ("INBOX", "CATEGORY_PROMOTIONS"),
                                  unsubscribe=True), "Newsletters and marketing")

    def test_notification(self):
        self.assertEqual(self.cat("Service <noreply@service.io>", "Weekly summary", ("INBOX", "CATEGORY_UPDATES")),
                         "Notifications and automated")

    def test_unknown_is_other(self):
        self.assertEqual(self.cat("Someone <a@unknown-company.biz>", "Hi"), "Other / uncertain")

    def test_subject_keywords_fallback(self):
        self.assertEqual(self.cat("Billing <accounts@smallbiz.com.au>", "Invoice #123"), "Bills and payments")

    def test_work_domain_from_env(self):
        with mock.patch.dict(os.environ, {"GMAIL_WORK_DOMAINS": "mywork.com.au"}):
            c = classify(m("Boss <boss@mywork.com.au>", "Re: report?"))
        self.assertEqual(c.category, "Work")
        self.assertTrue(c.needs_reply)
        self.assertTrue(c.protected)

    def test_subdomain_does_not_match_lookalike(self):
        # "evilcommbank.com.au" must not count as commbank.com.au
        c = classify(m("Info <x@evilcommbank.com.au>", "Hello"))
        self.assertNotEqual(c.category, "Finance and banking")


class AttributeTests(unittest.TestCase):
    def test_urgent(self):
        c = classify(m("AGL <bills@agl.com.au>", "FINAL NOTICE: payment overdue"))
        self.assertTrue(c.urgent)

    def test_needs_reply_person_question(self):
        self.assertTrue(classify(m("Jess <jess@gmail.com>", "Dinner Friday?")).needs_reply)

    def test_newsletter_never_needs_reply(self):
        c = classify(m("News <news@gmail.com>", "Re: what's new?", unsubscribe=True))
        self.assertFalse(c.needs_reply)


class SpamTests(unittest.TestCase):
    def test_marketing_is_not_spam(self):
        c = classify(m("Shop <deals@shop.com>", "Huge sale ends tonight", ("INBOX", "CATEGORY_PROMOTIONS"),
                       unsubscribe=True))
        self.assertEqual(c.spam_level, "none")
        self.assertNotEqual(c.category, "Spam or suspicious")

    def test_brand_phishing_with_failed_auth_is_high(self):
        c = classify(m("PayPal Security <alert@paypa1-secure.xyz>", "Account suspended - verify your account",
                       auth=FAIL))
        self.assertEqual(c.category, "Spam or suspicious")
        self.assertEqual(c.spam_level, "high")
        self.assertGreaterEqual(c.spam_score, rules.SPAM_HIGH)

    def test_single_weak_signal_is_not_high(self):
        c = classify(m("Promo <promo@random.com>", "Act now"))
        self.assertNotEqual(c.spam_level, "high")

    def test_one_strong_signal_is_review_only(self):
        c = classify(m("Netflix <billing@netflx-help.com>", "Update payment"))
        self.assertEqual(c.spam_level, "review")

    def test_real_bank_failing_auth_is_never_auto_spam(self):
        # A genuine-looking bank email with a broken DMARC result is flagged, not moved.
        c = classify(m("CommBank <notify@commbank.com.au>", "Unusual activity on your account", auth=FAIL))
        self.assertTrue(c.protected)
        self.assertNotEqual(c.spam_level, "high")
        self.assertEqual(c.category, "Finance and banking")

    def test_security_alert_is_protected(self):
        c = classify(m("Google <no-reply@accounts.google.com>", "Security alert: new sign-in", auth=PASS))
        self.assertTrue(c.protected)
        self.assertEqual(c.spam_level, "none")

    def test_thresholds(self):
        self.assertLess(rules.SPAM_REVIEW, rules.SPAM_HIGH)
        self.assertLessEqual(rules.SPAM_HIGH, 1.0)

    def test_auth_parse(self):
        self.assertEqual(auth_results(FAIL), {"spf": "fail", "dkim": "fail", "dmarc": "fail"})
        self.assertEqual(auth_results(""), {})

    def test_sender_parts(self):
        self.assertEqual(sender_parts('"Jess S" <Jess@Gmail.com>'), ("jess s", "jess@gmail.com", "gmail.com"))
        self.assertEqual(sender_parts("garbage")[2], "")


class ProposalTests(unittest.TestCase):
    def test_spam_gets_only_spam_action(self):
        c = classify(m("PayPal <a@paypa1.xyz>", "Your account will be closed", auth=FAIL))
        acts = propose(c)
        self.assertEqual([a.kind for a in acts], ["spam"])

    def test_protected_never_proposed_for_spam(self):
        c = classify(m("NAB <alerts@nab.com.au>", "You have won a prize", auth=FAIL))
        self.assertNotIn("spam", [a.kind for a in propose(c)])

    def test_review_label(self):
        c = classify(m("Netflix <billing@netflx-help.com>", "Update payment"))
        self.assertIn("Agent/Review", [a.value for a in propose(c)])

    def test_other_gets_no_category_label(self):
        self.assertEqual(propose(classify(m("A <a@b-c.biz>", "Hi"))), [])

    def test_same_email_same_proposal(self):
        e = m("AGL <bills@agl.com.au>", "Payment due tomorrow")
        self.assertEqual(propose(classify(e)), propose(classify(e)))

    def test_report_counts(self):
        emails = [m("AGL <b@agl.com.au>", "Bill", i="1"),
                  m("PayPal <a@paypa1.xyz>", "Account suspended", auth=FAIL, i="2"),
                  m("Jess <jess@gmail.com>", "Lunch?", i="3")]
        r = build_report(emails)
        self.assertEqual(r.scanned, 3)
        self.assertEqual(r.spam_high, 1)
        self.assertEqual(r.needs_reply, 1)
        self.assertEqual(r.actions["move to Spam"], 1)
        self.assertNotIn("jess", r.counts_text().lower())
        self.assertIn("DRY RUN", r.counts_text())


class DryRunCliTests(unittest.TestCase):
    def run_cli(self, env, argv, data):
        client = FakeClient(data)
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), redirect_stdout(out), \
                mock.patch.object(cli, "build_client", return_value=client):
            code = cli.main(argv)
        return code, out.getvalue(), client

    def test_report_only_reads(self):
        data = [msg(1, sender="PayPal <a@paypa1.xyz>", subject="Account suspended")]
        code, out, client = self.run_cli({}, ["report"], data)
        self.assertEqual(code, 0)
        self.assertTrue(set(client.calls) <= {"messages.list", "messages.get", "labels.get"}, client.calls)
        self.assertIn("nothing in Gmail was changed", out)

    def test_report_private_on_github(self):
        data = [msg(1, sender="Jess <jess.private@gmail.com>", subject="Secret plans?")]
        _, out, _ = self.run_cli({"GITHUB_ACTIONS": "true"}, ["report", "--samples", "5"], data)
        self.assertNotIn("jess.private", out)
        self.assertNotIn("Secret plans", out)

    def test_report_samples_locally(self):
        data = [msg(1, sender="Jess <jess@gmail.com>", subject="Lunch?")]
        _, out, _ = self.run_cli({}, ["report", "--samples", "5"], data)
        self.assertIn("Personal", out)
        self.assertIn("would label Agent/Personal", out)


if __name__ == "__main__":
    unittest.main()

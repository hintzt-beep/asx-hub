"""Rule-based email sorting. Uses headers and Gmail labels only: no email bodies, no AI, no cost.

Each email gets a main category plus attributes (urgent, needs a reply, protected) and a
spam score with plain-English reasons. Conservative by design: finance, bills, security and
work senders are "protected" and can never be proposed for Spam, only flagged for review.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from email.utils import parseaddr

from . import rules
from .gmail_service import MessageMeta

SPAM = "Spam or suspicious"
OTHER = "Other / uncertain"
PROTECTED_CATEGORIES = {"Work", "Finance and banking", "Bills and payments"}


@dataclass(frozen=True)
class Classification:
    message_id: str
    category: str
    confidence: float
    urgent: bool
    needs_reply: bool
    protected: bool
    spam_score: float
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def spam_level(self) -> str:
        """'high' = propose for Spam, 'review' = ask you, 'none' = leave alone."""
        if self.spam_score >= rules.SPAM_HIGH and not self.protected:
            return "high"
        if self.spam_score >= rules.SPAM_REVIEW:
            return "review"
        return "none"


def sender_parts(from_header: str) -> tuple[str, str, str]:
    """(display name, address, domain), all lower case."""
    name, addr = parseaddr(from_header or "")
    addr = addr.lower().strip()
    domain = addr.rsplit("@", 1)[1] if "@" in addr else ""
    return name.lower().strip(), addr, domain


def domain_in(domain: str, domains: list[str]) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in domains if d)


def _has(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def _work_domains() -> list[str]:
    extra = [d.strip().lower() for d in os.environ.get("GMAIL_WORK_DOMAINS", "").split(",")]
    return [d for d in rules.WORK_DOMAINS + extra if d]


def auth_results(header: str) -> dict[str, str]:
    """Read spf/dkim/dmarc results from Gmail's Authentication-Results header."""
    out = {}
    for check in ("spf", "dkim", "dmarc"):
        m = re.search(rf"\b{check}=(\w+)", header or "", re.I)
        if m:
            out[check] = m.group(1).lower()
    return out


def _brand_mismatch(name: str, domain: str) -> str | None:
    for brand, owned in rules.BRANDS.items():
        if re.search(rf"\b{re.escape(brand)}\b", name) and not domain_in(domain, owned):
            return brand
    return None


def spam_signals(meta: MessageMeta, name: str, domain: str) -> tuple[float, list[str]]:
    score, why = 0.0, []
    subject = meta.subject.lower()
    auth = auth_results(meta.headers.get("authentication-results", ""))
    if auth.get("dmarc") == "fail":
        score += 0.45; why.append("sender failed DMARC check")
    if auth.get("spf") in ("fail", "softfail") and auth.get("dkim") not in ("pass",):
        score += 0.3; why.append("sender failed SPF and has no valid DKIM")
    brand = _brand_mismatch(name, domain)
    if brand:
        score += 0.5; why.append(f"name says '{brand}' but email isn't from their domain")
    if _has(subject, rules.SCAM_SUBJECT):
        score += 0.35; why.append("scam-style subject")
    reply_to = sender_parts(meta.headers.get("reply-to", ""))[2]
    if reply_to and domain and reply_to != domain and not domain_in(reply_to, [domain]) \
            and not domain_in(domain, [reply_to]):
        score += 0.15; why.append("replies go to a different domain")
    if not domain:
        score += 0.2; why.append("no valid sender address")
    return min(score, 1.0), why


def classify(meta: MessageMeta) -> Classification:
    name, addr, domain = sender_parts(meta.sender)
    subject = meta.subject.lower()
    labels = meta.labels
    reasons: list[str] = []
    automated = "list-unsubscribe" in meta.headers or _has(addr, rules.NOREPLY_HINTS)

    security = domain_in(domain, rules.SECURITY_DOMAINS) and _has(subject, rules.SECURITY_SUBJECT)
    category, confidence = OTHER, 0.3

    if domain_in(domain, _work_domains()):
        category, confidence = "Work", 0.95; reasons.append("work domain")
    elif domain_in(domain, rules.FINANCE_DOMAINS):
        category, confidence = "Finance and banking", 0.9; reasons.append("bank/finance sender")
    elif domain_in(domain, rules.BILLS_DOMAINS):
        category, confidence = "Bills and payments", 0.9; reasons.append("bill sender")
    elif domain_in(domain, rules.TRAVEL_DOMAINS):
        category, confidence = "Travel and bookings", 0.9; reasons.append("travel sender")
    elif domain_in(domain, rules.SHOPPING_DOMAINS):
        category, confidence = "Shopping and orders", 0.85; reasons.append("shop sender")
    elif security:
        category, confidence = "Notifications and automated", 0.9; reasons.append("security/account alert")
    else:
        for cat, words in rules.SUBJECT_KEYWORDS.items():
            if _has(subject, words):
                category, confidence = cat, 0.6; reasons.append("subject keywords")
                break
        else:
            if domain_in(domain, rules.PERSONAL_DOMAINS) and not automated:
                category, confidence = "Personal", 0.8; reasons.append("from a person's email")
            elif "CATEGORY_PROMOTIONS" in labels or "CATEGORY_SOCIAL" in labels or "CATEGORY_FORUMS" in labels:
                category, confidence = "Newsletters and marketing", 0.8; reasons.append("Gmail Promotions/Social tab")
            elif "list-unsubscribe" in meta.headers:
                category, confidence = "Newsletters and marketing", 0.7; reasons.append("has unsubscribe link")
            elif "CATEGORY_UPDATES" in labels or automated:
                category, confidence = "Notifications and automated", 0.7; reasons.append("automated sender")
            elif "CATEGORY_PERSONAL" in labels and not automated:
                category, confidence = "Personal", 0.6; reasons.append("Gmail Primary tab, not automated")

    protected = category in PROTECTED_CATEGORIES or security
    spam_score, spam_why = spam_signals(meta, name, domain)
    if spam_score >= rules.SPAM_REVIEW:
        reasons.extend(spam_why)
        if not protected:
            category, confidence = SPAM, spam_score
        else:
            reasons.append("looks like a protected sender: flagged for review, never auto-spammed")

    urgent = category != SPAM and (_has(subject, rules.URGENT_SUBJECT) or
                                   ("IMPORTANT" in labels and _has(subject, rules.SECURITY_SUBJECT)))
    needs_reply = (category in ("Personal", "Work") and not automated and
                   (subject.startswith("re:") or "?" in subject or "IMPORTANT" in labels))

    return Classification(
        message_id=meta.id, category=category, confidence=round(confidence, 2), urgent=urgent,
        needs_reply=needs_reply, protected=protected, spam_score=round(spam_score, 2), reasons=tuple(reasons),
    )

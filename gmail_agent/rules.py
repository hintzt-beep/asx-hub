"""Sorting rules. Edit these lists to tune the agent: no code changes needed elsewhere.

Matching uses only headers Gmail already gives us (sender, subject, labels, sign-in checks).
Domains match the sender's domain and any subdomain (e.g. "commbank.com.au" matches
"notify.commbank.com.au").
"""
from __future__ import annotations

# Main categories, in the order they are checked. The first match wins.
CATEGORIES = [
    "Work",
    "Finance and banking",
    "Bills and payments",
    "Travel and bookings",
    "Shopping and orders",
    "Personal",
    "Newsletters and marketing",
    "Notifications and automated",
    "Spam or suspicious",
    "Other / uncertain",
]

# Your own work email domains (add yours, e.g. "mycompany.com.au"). Also settable with
# the GMAIL_WORK_DOMAINS environment variable, comma separated.
WORK_DOMAINS: list[str] = []

FINANCE_DOMAINS = [
    "commbank.com.au", "commsec.com.au", "nab.com.au", "westpac.com.au", "anz.com", "anz.com.au",
    "ing.com.au", "macquarie.com", "macquarie.com.au", "stgeorge.com.au", "bankofmelbourne.com.au",
    "banksa.com.au", "suncorp.com.au", "bendigobank.com.au", "boq.com.au", "ubank.com.au", "up.com.au",
    "paypal.com", "paypal.com.au", "coinspot.com.au", "afterpay.com", "zip.co", "wise.com",
    "selfwealth.com.au", "stake.com.au", "superhero.com.au", "australiansuper.com", "hostplus.com.au",
    "ato.gov.au", "my.gov.au", "servicesaustralia.gov.au",
]
BILLS_DOMAINS = [
    "agl.com.au", "originenergy.com.au", "energyaustralia.com.au", "redenergy.com.au", "alintaenergy.com.au",
    "telstra.com", "telstra.com.au", "optus.com.au", "vodafone.com.au", "tpg.com.au", "aussiebroadband.com.au",
    "sydneywater.com.au", "linkt.com.au", "budgetdirect.com.au", "nrma.com.au", "racv.com.au", "aami.com.au",
    "medibank.com.au", "bupa.com.au", "hcf.com.au",
]
TRAVEL_DOMAINS = [
    "qantas.com", "qantas.com.au", "virginaustralia.com", "jetstar.com", "rex.com.au", "booking.com",
    "airbnb.com", "expedia.com", "expedia.com.au", "agoda.com", "hotels.com", "webjet.com.au", "uber.com",
    "trip.com", "skyscanner.net",
]
SHOPPING_DOMAINS = [
    "amazon.com", "amazon.com.au", "ebay.com", "ebay.com.au", "jbhifi.com.au", "kmart.com.au", "bigw.com.au",
    "woolworths.com.au", "coles.com.au", "temu.com", "shein.com", "aliexpress.com", "officeworks.com.au",
    "bunnings.com.au", "myer.com.au", "davidjones.com", "catch.com.au", "thegoodguys.com.au",
    "auspost.com.au", "startrack.com.au", "sendle.com", "doordash.com", "menulog.com.au",
]
# Big email providers: a sender here is a person, not a company.
PERSONAL_DOMAINS = [
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "live.com.au", "icloud.com",
    "me.com", "yahoo.com", "yahoo.com.au", "bigpond.com", "bigpond.net.au", "optusnet.com.au", "proton.me",
    "protonmail.com",
]
# Security and account-recovery senders: never treated as spam.
SECURITY_DOMAINS = [
    "accounts.google.com", "google.com", "microsoft.com", "accountprotection.microsoft.com", "apple.com",
    "id.apple.com", "github.com", "anthropic.com", "supabase.com", "supabase.io",
]

SUBJECT_KEYWORDS = {
    "Finance and banking": ["statement", "transaction", "transfer", "deposit", "withdrawal", "dividend",
                            "trade confirmation", "contract note", "tax return", "interest"],
    "Bills and payments": ["invoice", "bill", "payment due", "amount due", "receipt", "direct debit",
                           "renewal", "overdue", "premium"],
    "Travel and bookings": ["booking", "itinerary", "flight", "check-in", "boarding pass", "reservation",
                            "your trip", "e-ticket"],
    "Shopping and orders": ["your order", "order confirmation", "has shipped", "dispatched", "delivered",
                            "tracking", "out for delivery", "refund"],
}
SECURITY_SUBJECT = ["security alert", "sign-in", "sign in", "verification code", "verify your email",
                    "password", "2-step", "two-factor", "new device", "recovery", "login attempt"]
URGENT_SUBJECT = ["urgent", "action required", "action needed", "immediately", "final notice", "overdue",
                  "due today", "due tomorrow", "expires", "expiring", "last chance to pay", "asap",
                  "response required", "deadline"]
# Phishing and scam phrases (in the subject). Only one signal among several.
SCAM_SUBJECT = ["you have won", "you've won", "claim your prize", "lottery", "inheritance", "gift card",
                "bitcoin giveaway", "crypto giveaway", "double your", "account suspended",
                "account has been suspended", "unusual activity", "confirm your identity", "verify your account",
                "your account will be closed", "wire transfer", "beneficiary", "investment opportunity",
                "guaranteed return", "act now", "100% free"]
# Brand names that scammers fake. If the display name says one of these but the sender's
# domain isn't theirs, that's a strong phishing signal.
BRANDS = {
    "commbank": ["commbank.com.au", "cba.com.au"], "commonwealth bank": ["commbank.com.au", "cba.com.au"],
    "westpac": ["westpac.com.au"], "nab": ["nab.com.au"], "anz": ["anz.com", "anz.com.au"],
    "paypal": ["paypal.com", "paypal.com.au"], "netflix": ["netflix.com"], "apple": ["apple.com", "icloud.com"],
    "microsoft": ["microsoft.com", "outlook.com"], "google": ["google.com"], "amazon": ["amazon.com", "amazon.com.au"],
    "auspost": ["auspost.com.au"], "australia post": ["auspost.com.au"], "mygov": ["my.gov.au"],
    "ato": ["ato.gov.au"], "linkt": ["linkt.com.au"], "telstra": ["telstra.com", "telstra.com.au"],
    "coinspot": ["coinspot.com.au"], "commsec": ["commsec.com.au"],
}
NOREPLY_HINTS = ["noreply", "no-reply", "donotreply", "do-not-reply", "notifications", "notification",
                 "alerts", "mailer", "news", "info@", "hello@", "updates", "support@", "team@"]

# Spam confidence thresholds (0 to 1).
SPAM_HIGH = 0.9      # at or above: proposed for the Spam folder (only acted on once actions exist and dry-run is off)
SPAM_REVIEW = 0.5    # between REVIEW and HIGH: flagged for you to review, never moved automatically

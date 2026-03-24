"""Email pre-filter — drops sensitive AND irrelevant emails.

Two passes:
1. Privacy gate: drops medical, financial, legal (never reaches any LLM)
2. Relevance gate: drops marketing, newsletters, university bulk mail

Only personally interesting emails survive.
"""

from __future__ import annotations

import re

# ── Privacy gate (sensitive content) ─────────────────────────────────

SENSITIVE_DOMAINS = [
    "mychart", "patient", "health", "medical", "pharmacy",
    "bank", "chase", "wellsfargo", "citibank", "payroll", "irs.gov",
    "courts.", "legal", "attorney", "lawfirm",
    "insurance", "claim",
]

SENSITIVE_SUBJECTS = [
    re.compile(r"(?i)(diagnosis|prescription|lab results|appointment.*dr|medical|hipaa)"),
    re.compile(r"(?i)(statement|balance|payment due|wire transfer|tax return|w-2|1099)"),
    re.compile(r"(?i)(court date|subpoena|legal notice|custody|restraining)"),
    re.compile(r"(?i)(std |hiv|pregnancy|therapy|counseling|rehab)"),
    re.compile(r"(?i)(password reset|verify your identity|security alert|suspicious sign)"),
]

# ── Relevance gate (noise) ───────────────────────────────────────────

SPAM_DOMAINS = [
    # Marketing / promo
    "lyft", "uber.com", "doordash", "grubhub", "seamless",
    "zillow", "redfin", "apartments.com",
    "xbox", "playstation", "steam", "epicgames", "nintendo",
    "belk", "gap.com", "oldnavy", "hm.com", "zara",
    "hulu", "netflix", "spotify", "disneyplus", "peacock", "paramountplus",
    "panera", "starbucks", "chipotle", "sweetgreen",
    "linkedin.com", "quora", "medium.com", "substack",
    "amazon.com", "target.com", "walmart.com", "bestbuy",
    "mint.com", "creditkarma", "nerdwallet",
    # Newsletters / mass media
    "nytimes.com", "washingtonpost.com", "wsj.com",
    "newyorker.com", "theatlantic.com", "vox.com",
    "cnn.com", "foxnews", "msnbc", "bbc.com",
    "morningbrew", "theskim", "axios.com",
    # Job platforms (mass alerts, not personal)
    "handshake.com", "indeed.com", "glassdoor",
    "devpost", "angellist", "wellfound",
    "ticketmaster", "stubhub", "seatgeek", "livenation",
    "turnoutpac", "actblue", "winred", "political", "survey",
    "agenttraining", "realtyexecutives", "kw.com",
    "uniqlo", "nike.com", "adidas",
    # University bulk
    "nyu.edu", "newschool.edu",
    # Tech marketing
    "openrouter", "edgeimpulse", "productstunt",
    "github.com/notifications", "gitlab",
    # Advocacy / political / surveys
    "tirrc", "nba.com", "realty", "surveymonkey", "typeform",
    "politico", "campaignmonitor", "nationbuilder",
]

SPAM_SUBJECTS = [
    re.compile(r"(?i)(unsubscribe|opt.out|email preferences|manage.*subscription)"),
    re.compile(r"(?i)(% off|free shipping|limited.time|flash sale|deal of|clearance|promo code)"),
    re.compile(r"(?i)(weekly digest|daily digest|newsletter|weekly buzz|weekly recap|morning brief)"),
    re.compile(r"(?i)(we miss you|come back|it's been a while|don't miss out|last chance)"),
    re.compile(r"(?i)(top picks for you|recommended for you|you might like|trending now)"),
    re.compile(r"(?i)(claim your|activate your|verify your email|confirm your)"),
    re.compile(r"(?i)(just posted a role|similar jobs|new jobs|job alert|career opportunity)"),
    re.compile(r"(?i)(ITP announce|ITP weekly|campus event|student council|NYU IT)"),
]

# ── Emails we ALWAYS keep (override spam filters) ────────────────────

KEEP_SUBJECTS = [
    re.compile(r"(?i)(invitation|invited you|rsvp|you're in|accepted|confirmed)"),
    re.compile(r"(?i)(receipt|order confirm|booking confirm|reservation confirmed|your ticket|e-ticket)"),
    re.compile(r"(?i)(applied to|application.*received|thank you for applying)"),
    re.compile(r"(?i)(you received money|payment from|sent you|venmo|zelle)"),
]


def _extract_email_address(sender: str) -> str:
    """Extract the bare email address from a sender string.

    Handles formats like:
      - "john@example.com"
      - "John Smith <john@example.com>"
      - "<john@example.com>"
    Falls back to the full sender string (lowered) if no angle brackets found.
    """
    import re
    match = re.search(r"<([^>]+)>", sender)
    if match:
        return match.group(1).lower().strip()
    # No angle brackets — might be a bare email
    return sender.lower().strip()


def filter_emails(emails: list[dict]) -> list[dict]:
    """Remove sensitive and irrelevant emails. Returns only useful ones."""
    useful = []
    for em in emails:
        raw_sender = em.get("from", "")
        email_addr = _extract_email_address(raw_sender)
        subject = em.get("subject", "")

        # Pass 1: Privacy — always drop sensitive
        if any(d in email_addr for d in SENSITIVE_DOMAINS):
            continue
        if any(p.search(subject) for p in SENSITIVE_SUBJECTS):
            continue

        # Pass 2: Check if it's a keeper (override spam check)
        is_keeper = any(p.search(subject) for p in KEEP_SUBJECTS)
        if is_keeper:
            useful.append(em)
            continue

        # Pass 3: Relevance — drop spam/marketing/newsletters
        if any(d in email_addr for d in SPAM_DOMAINS):
            continue
        if any(p.search(subject) for p in SPAM_SUBJECTS):
            continue

        useful.append(em)
    return useful

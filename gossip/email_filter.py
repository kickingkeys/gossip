"""Code-level email sensitivity pre-filter.

Drops sensitive emails BEFORE they reach any LLM.
This is a privacy gate — pure pattern matching, no LLM call.
"""

from __future__ import annotations

import re

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


def filter_emails(emails: list[dict]) -> list[dict]:
    """Remove sensitive emails. Returns only safe-to-process emails."""
    safe = []
    for em in emails:
        sender = em.get("from", "").lower()
        subject = em.get("subject", "")

        # Domain check
        if any(d in sender for d in SENSITIVE_DOMAINS):
            continue

        # Subject pattern check
        if any(p.search(subject) for p in SENSITIVE_SUBJECTS):
            continue

        safe.append(em)
    return safe

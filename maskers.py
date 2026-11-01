"""Masking strategies and role policies with Quantum Entropy integration."""
from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

REDACTED = "[REDACTED]"
BUCKETS = [0, 1_000, 10_000, 50_000, 100_000, 500_000, 1_000_000]

# Role-based action policies
POLICIES = {
    "admin": {
        "*": "none",
    },
    "support": {
        "PII_HIGH": "partial",
        "PII_MEDIUM": "partial",
        "FINANCIAL_CONFIDENTIAL": "partial",
        "NON_SENSITIVE": "none",
        "UNSCANNED": "redact",
    },
    "analyst": {
        "PII_HIGH": "hash",
        "PII_MEDIUM": "redact",
        "FINANCIAL_CONFIDENTIAL": "redact",
        "NON_SENSITIVE": "none",
        "UNSCANNED": "redact",
    },
}


def action_for(role: str, tag: str) -> str:
    """Fail closed: unknown role or unknown tag defaults to redact."""
    role_lower = (role or "").strip().lower()
    policy = POLICIES.get(role_lower)
    if policy is None:
        return "redact"
    return policy.get(tag, policy.get("*", "redact"))


def _bucket(value: Any) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return REDACTED
    if x < 0:
        return "< 0"
    for lo, hi in zip(BUCKETS, BUCKETS[1:]):
        if x < hi:
            return f"{lo:,}-{hi:,}"
    return f"{BUCKETS[-1]:,}+"


def _normalize_for_hash(val: Any, data_type: str | None) -> str:
    s = str(val).strip()
    dt = (data_type or "").lower()
    if dt in ("card", "credit_card", "ssn", "phone", "iban", "account_number"):
        return re.sub(r"\D", "", s)
    if dt == "email":
        return s.lower()
    return s


def hash_value(value: Any, quantum_secret: str, data_type: str | None = None, hex_chars: int = 16) -> str | None:
    """Deterministic HMAC-SHA3-256 keyed with Quantum Entropy.

    Ensures mathematical joinability across analytical tables without leaking raw PII.
    """
    if value is None:
        return None
    normalized = _normalize_for_hash(value, data_type)
    digest = hmac.new(
        quantum_secret.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha3_256,
    ).hexdigest()
    return "h_" + digest[:hex_chars]


def partial_mask(value: Any, data_type: str | None) -> str | None:
    if value is None:
        return None
    dt = (data_type or "").lower()

    if dt == "balance":
        return _bucket(value)

    s = str(value).strip()

    if dt in ("card", "credit_card"):
        # 4111-XXXX-XXXX-1111: keep first 4 and last 4 digits, replace middle digits with X
        digits = [i for i, c in enumerate(s) if c.isdigit()]
        if len(digits) >= 8:
            keep = set(digits[:4]) | set(digits[-4:])
            return "".join(c if (not c.isdigit() or i in keep) else "X" for i, c in enumerate(s))
        return "XXXX-XXXX-XXXX-" + (s[-4:] if len(s) >= 4 else "XXXX")

    if dt in ("ssn", "notes"):
        # XXX-XX-6789: every digit except last 4 becomes X
        digits = [i for i, c in enumerate(s) if c.isdigit()]
        if len(digits) >= 4:
            keep = set(digits[-4:])
            return "".join(c if (not c.isdigit() or i in keep) else "X" for i, c in enumerate(s))
        return "XXX-XX-" + s[-4:] if len(s) >= 4 else "XXX-XX-XXXX"

    if dt == "phone":
        # +X (XXX) XXX-0134: keep last 4 digits, obscure earlier digits
        digits = [i for i, c in enumerate(s) if c.isdigit()]
        if len(digits) >= 4:
            keep = set(digits[-4:])
            return "".join(c if (not c.isdigit() or i in keep) else "X" for i, c in enumerate(s))
        return "+X (XXX) XXX-" + (s[-4:] if len(s) >= 4 else "XXXX")

    if dt in ("account_number", "acct_number", "aadhaar"):
        # XXXXXX3000: keep last 4 digits, replace preceding digits with X
        digits = [i for i, c in enumerate(s) if c.isdigit()]
        if len(digits) >= 4:
            keep = set(digits[-4:])
            return "".join(c if (not c.isdigit() or i in keep) else "X" for i, c in enumerate(s))
        return "XXXXXX" + s[-4:] if len(s) >= 4 else "XXXXXXXX"

    if dt == "iban":
        # DEXXXXXXXXXXXXXXXX3000: keep first 2 and last 4 characters, rest X
        if len(s) > 6:
            return s[:2] + ("X" * (len(s) - 6)) + s[-4:]
        return s[:2] + "XXXXXXXX"

    if dt == "email":
        # a***@example.com: first char of local part, ***, then @domain
        local, _, domain = s.partition("@")
        return f"{local[:1]}***@{domain}" if domain else "***"

    if dt == "dob":
        # 1990-XX-XX: year only
        m = re.match(r"^(\d{4})[-/]", s)
        return f"{m.group(1)}-XX-XX" if m else "XXXX-XX-XX"

    if dt in ("person_name", "first_name", "last_name", "full_name", "holder_name"):
        parts = s.split()
        return " ".join(p[:1] + "***" for p in parts) if parts else "***"

    if dt == "address":
        return s[:1] + "***" if s else "***"

    if dt in ("ip_address", "ip"):
        parts = s.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.X.X"
        return "X.X.X.X"

    if dt == "pan":
        # ABXXX0000F: mask the letters except the first two and the final check char
        digits = [i for i, c in enumerate(s) if c.isdigit()]
        alphas = [i for i, c in enumerate(s) if c.isalpha()]
        if len(digits) == 4 and len(alphas) >= 6:
            keep = {alphas[0], alphas[1], alphas[-1]} | set(digits)
            return "".join(c if (not c.isalpha() or i in keep) else "X" for i, c in enumerate(s))
        return "XXXXX0000F"

    # Default fallback
    return s[:1] + "***" if len(s) > 1 else "***"


# Free-text PII scrubbing for restricted roles (never raw PII in logs / UI)
SCRUB_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("pan", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    ("card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("phone", re.compile(r"\b(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}\b")),
    ("phone", re.compile(r"\b(?:\+91[\s-]?)?\d{5}[\s-]?\d{5}\b")),
    ("aadhaar", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("ssn", re.compile(r"\b\d{3}[\s-]\d{2}[\s-]\d{4}\b")),
]


def scrub_text_pii(value: Any) -> Any:
    """Masks PII patterns embedded inside untagged (e.g. note) text columns."""
    if value is None or not isinstance(value, str) or not value.strip():
        return value
    out = value
    for dtype, pattern in SCRUB_PATTERNS:
        out = pattern.sub(lambda m: partial_mask(m.group(0), dtype), out)
    return out


def apply_mask(value: Any, action: str, data_type: str | None, quantum_secret: str) -> Any:
    if value is None or action == "none":
        return value
    if action == "redact":
        return REDACTED
    if action == "hash":
        return hash_value(value, quantum_secret, data_type)
    if action == "partial":
        return partial_mask(value, data_type)
    return REDACTED

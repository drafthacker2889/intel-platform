"""Tiered risk-keyword lexicons used by the rule-based scorer and featurizer.

These are intentionally kept as plain data so downstream users can extend or
replace them without touching scoring logic.
"""

RISK_KEYWORDS_CRITICAL = [
    "password", "passwd", "db_pass", "secret", "credentials", "leaked",
    "dump", "admin", "root", "backdoor", "api_key", "private_key",
    "access_token", "master_key", "encryption_key",
]

RISK_KEYWORDS_HIGH = [
    "exploit", "vulnerability", "cve", "zero-day", "0day", "malware",
    "ransomware", "phishing", "breach", "bypass", "shellcode", "payload",
    "lateral", "persistence", "c2", "command and control", "botnet",
]

RISK_KEYWORDS_MEDIUM = [
    "security", "audit", "penetration", "pentest", "recon", "unauthorized",
    "suspicious", "incident", "threat", "attack", "scan", "enumeration",
]

# Flat union used by the rule engine (critical + high tiers).
RISK_KEYWORDS = RISK_KEYWORDS_CRITICAL + RISK_KEYWORDS_HIGH

# Terms that, when co-occurring with any risk keyword, escalate the score.
AUTH_CONTEXT_TERMS = ("login", "credential", "credentials", "auth")


def matched_keywords(text_lower: str) -> dict:
    """Return the keywords found in already-lowercased ``text``, grouped by tier."""
    return {
        "critical": [w for w in RISK_KEYWORDS_CRITICAL if w in text_lower],
        "high": [w for w in RISK_KEYWORDS_HIGH if w in text_lower],
        "medium": [w for w in RISK_KEYWORDS_MEDIUM if w in text_lower],
    }

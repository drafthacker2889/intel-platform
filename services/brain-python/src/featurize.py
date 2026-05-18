import re

# ── Tiered keyword lists ───────────────────────────────────────────────────────
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

# Flat union used for backward-compatibility (training scripts, rules engine)
RISK_KEYWORDS = RISK_KEYWORDS_CRITICAL + RISK_KEYWORDS_HIGH

# ── Compiled regex patterns ────────────────────────────────────────────────────
_IP_RE    = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
_EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')
_HASH_RE  = re.compile(r'\b[a-fA-F0-9]{32,64}\b')
_URL_RE   = re.compile(r'https?://')


def featurize(text: str, entities: list) -> list:
    """
    Return a 12-element feature vector for risk classification.

    Features (in order):
      0  critical_keyword_hits  — count of CRITICAL-tier keywords found
      1  high_keyword_hits      — count of HIGH-tier keywords found
      2  medium_keyword_hits    — count of MEDIUM-tier keywords found
      3  entity_count           — number of named entities extracted
      4  text_length_norm       — len(text)/100, capped at 100
      5  ip_count               — IPv4 address occurrences
      6  email_count            — email address occurrences
      7  url_count              — http/https URL occurrences
      8  hash_count             — hex strings 32-64 chars (hashes, keys)
      9  at_count               — raw '@' symbol count
      10 urgency_count          — '!' characters (urgency signals)
      11 allcaps_word_count     — ALL-CAPS words longer than 2 chars
    """
    text_lower = text.lower()

    critical_hits = sum(1 for w in RISK_KEYWORDS_CRITICAL if w in text_lower)
    high_hits     = sum(1 for w in RISK_KEYWORDS_HIGH     if w in text_lower)
    medium_hits   = sum(1 for w in RISK_KEYWORDS_MEDIUM   if w in text_lower)

    ip_count      = len(_IP_RE.findall(text))
    email_count   = len(_EMAIL_RE.findall(text))
    url_count     = len(_URL_RE.findall(text))
    hash_count    = len(_HASH_RE.findall(text))
    at_count      = text.count("@")
    urgency_count = text.count("!")
    allcaps_count = sum(1 for w in text.split() if w.isupper() and len(w) > 2)

    return [
        critical_hits,
        high_hits,
        medium_hits,
        len(entities),
        min(len(text) / 100.0, 100.0),
        ip_count,
        email_count,
        url_count,
        hash_count,
        at_count,
        urgency_count,
        allcaps_count,
    ]

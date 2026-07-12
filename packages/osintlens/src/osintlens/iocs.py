"""Indicator-of-compromise (IOC) extraction.

Pure-Python, dependency-free. Returns the *actual* matched values (not just
counts), deduplicated while preserving first-seen order.
"""

import re
from typing import Dict, List

_IPV4_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_URL_RE = re.compile(r"\bhttps?://[^\s<>\"')]+", re.IGNORECASE)
_HASH_RE = re.compile(r"\b[a-fA-F0-9]{32,64}\b")
_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
# Base58 Bitcoin address (P2PKH / P2SH). Coarse but useful for triage.
_BTC_RE = re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b")

# IOC keys, in a stable order for display / serialization.
IOC_TYPES = ("ipv4", "email", "url", "md5", "sha1", "sha256", "cve", "btc")


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    out = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def extract_iocs(text: str) -> Dict[str, List[str]]:
    """Extract indicators from ``text``.

    Hashes are bucketed by length: 32=md5, 40=sha1, 64=sha256. Other hex
    lengths in the 32-64 range are dropped as ambiguous.
    """
    hashes = _HASH_RE.findall(text)
    md5 = [h for h in hashes if len(h) == 32]
    sha1 = [h for h in hashes if len(h) == 40]
    sha256 = [h for h in hashes if len(h) == 64]

    return {
        "ipv4": _dedupe(_IPV4_RE.findall(text)),
        "email": _dedupe(_EMAIL_RE.findall(text)),
        "url": _dedupe(_URL_RE.findall(text)),
        "md5": _dedupe(md5),
        "sha1": _dedupe(sha1),
        "sha256": _dedupe(sha256),
        "cve": _dedupe([c.upper() for c in _CVE_RE.findall(text)]),
        "btc": _dedupe(_BTC_RE.findall(text)),
    }


def ioc_count(iocs: Dict[str, List[str]]) -> int:
    """Total number of indicators across all types."""
    return sum(len(v) for v in iocs.values())

"""Ground-truth IOC synthesis.

Generates realistic-looking indicators and a short multilingual sentence that
embeds them. Because the values are known at generation time, each sample can
carry its indicators as ground truth — turning the dataset into a benchmark
for IOC-extraction tools, not just risk classifiers.

All values are synthetic. IPs are drawn from RFC 5737 documentation ranges and
domains from RFC 2606 reserved names, so nothing points at a real host.
"""

import random
from typing import Dict, List

# RFC 5737 TEST-NET blocks — guaranteed non-routable / documentation-only.
_DOC_IP_PREFIXES = ("192.0.2.", "198.51.100.", "203.0.113.")
# RFC 2606 reserved TLDs/domains — safe for examples.
_DOC_DOMAINS = ("example.com", "example.org", "example.net", "test.example")
_USERS = ("admin", "root", "svc-backup", "j.doe", "support", "billing")

_EMBED_TEMPLATES = {
    "en": " Contact {email}; C2 at {ip}; sample {sha256}; ref {cve}.",
    "ru": " Контакт {email}; C2 на {ip}; образец {sha256}; см. {cve}.",
    "zh": " 联系 {email}；C2 位于 {ip}；样本 {sha256}；参见 {cve}。",
    "de": " Kontakt {email}; C2 unter {ip}; Probe {sha256}; siehe {cve}.",
}


def _sha256(rng: random.Random) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(64))


def _ip(rng: random.Random) -> str:
    return rng.choice(_DOC_IP_PREFIXES) + str(rng.randint(1, 254))


def _email(rng: random.Random) -> str:
    return f"{rng.choice(_USERS)}@{rng.choice(_DOC_DOMAINS)}"


def _cve(rng: random.Random) -> str:
    return f"CVE-{rng.randint(2015, 2025)}-{rng.randint(1000, 99999)}"


def synth_iocs(rng: random.Random) -> Dict[str, List[str]]:
    """Return a dict of freshly generated synthetic indicators."""
    return {
        "ipv4": [_ip(rng)],
        "email": [_email(rng)],
        "sha256": [_sha256(rng)],
        "cve": [_cve(rng)],
    }


def embed_iocs(text: str, lang: str, iocs: Dict[str, List[str]]) -> str:
    """Append a language-appropriate sentence embedding ``iocs`` into ``text``."""
    template = _EMBED_TEMPLATES.get(lang, _EMBED_TEMPLATES["en"])
    return text + template.format(
        email=iocs["email"][0],
        ip=iocs["ipv4"][0],
        sha256=iocs["sha256"][0],
        cve=iocs["cve"][0],
    )

"""
Generate a large, diverse, adversarially-hardened ML training dataset.

Produces 50,000 labeled English samples with:
- 4 risk tiers: CRITICAL / HIGH / MEDIUM / LOW
- Multiple writing styles per tier (forum post, paste dump, news article, chat log)
- Adversarial "false-positive" examples: benign text containing risk keywords in
  context that should not trigger high risk
- Adversarial "false-negative" examples: risky text without obvious keywords
- Borderline examples deliberately near category boundaries

Usage:
    python generate_synthetic_data.py          # 50K samples (default)
    python generate_synthetic_data.py --n 20000
"""

import argparse
import json
import random
import re
from pathlib import Path
from typing import Dict, List, Tuple

random.seed(42)


# ── Vocabulary pools ───────────────────────────────────────────────────────────

ACTORS = [
    "LockBit 3.0", "BlackCat/ALPHV", "Royal Ransomware", "Cl0p", "Evil Corp",
    "Lazarus Group", "APT28 (Fancy Bear)", "APT29 (Cozy Bear)", "Carbanak",
    "FIN7", "REvil", "Conti", "DarkSide", "BlackMatter", "Hive",
    "Play Ransomware", "BianLian", "Vice Society", "AvosLocker", "Karakurt",
    "Anonymous group", "ShinyHunters", "GhostSec", "Killnet", "Scattered Spider",
]

ORGS = [
    "a major US hospital network", "a Fortune 500 retailer", "a European bank",
    "a US federal contractor", "a regional law firm", "a state government agency",
    "a major university", "a global insurance company", "a defense subcontractor",
    "a municipal water authority", "a telecoms provider", "a shipping company",
    "a pharmaceutical company", "an energy utility", "a media conglomerate",
]

TECHNOLOGIES = [
    "Windows Server 2019", "Active Directory", "Exchange Server", "Cisco ASA",
    "FortiGate VPN", "Pulse Secure VPN", "VMware ESXi", "Apache Log4j",
    "Microsoft Exchange ProxyLogon", "SolarWinds Orion", "Atlassian Confluence",
    "MOVEit Transfer", "GoAnywhere MFT", "Citrix NetScaler", "F5 BIG-IP",
    "Palo Alto GlobalProtect", "Ivanti Connect Secure", "TeamViewer",
]

CVE_IDS = [
    "CVE-2024-3400", "CVE-2024-21762", "CVE-2023-46604", "CVE-2023-44487",
    "CVE-2023-4966",  "CVE-2023-34362", "CVE-2022-47966", "CVE-2021-44228",
    "CVE-2021-26855", "CVE-2020-1472",  "CVE-2019-19781", "CVE-2018-13379",
]

DARK_WEB_HANDLES = [
    "th3_archiv1st", "d4rkn3t_sell3r", "r00t_access", "cr3d_dump3r",
    "ghost_hunter99", "shadowbroker_x", "null_byte_666", "xpl0it_m4st3r",
    "b4ckd00r_king", "ransom_lord",
]

COUNTRIES = [
    "Russia", "China", "North Korea", "Iran", "Ukraine", "Romania",
    "Nigeria", "Brazil", "the United States", "Germany",
]

SAMPLE_PASSWORDS = [
    "P@ssw0rd!", "Summer2024!", "Welcome1!", "Admin123!", "Letmein#1",
    "[REDACTED]", "***hidden***", "hunter2", "qwerty123!", "Company@2024",
]

SAMPLE_IPS = [
    "192.168.1.254", "10.0.0.1", "172.16.0.100", "45.67.231.45",
    "104.21.89.6", "185.220.101.45", "91.108.4.1",
]

SAMPLE_HASHES = [
    "5f4dcc3b5aa765d61d8327deb882cf99",
    "e10adc3949ba59abbe56e057f20f883e",
    "098f6bcd4621d373cade4e832627b4f6",
    "d8578edf8458ce06fbc5bb76a58c5ca4",
]

SAMPLE_DOMAINS = [
    "internal.corp.example", "admin.company.local", "vpn.target-org.com",
    "mail.victim-corp.net", "dc01.domain.internal",
]


# ── Template builders by writing style ────────────────────────────────────────

def _forum_post(body: str) -> str:
    prefixes = [
        "Re: [SELLING]", "OP:", "UPDATE:", "[THREAD]", "New post by user:",
        f"{random.choice(DARK_WEB_HANDLES)} posted:", "Forum post:",
    ]
    return f"{random.choice(prefixes)} {body}"


def _paste_dump(body: str) -> str:
    ts = f"2024-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
    prefixes = [
        f"# Paste uploaded {ts}\n", f"--- BEGIN DUMP ---\n",
        f"# Source: underground market\n", "",
    ]
    return f"{random.choice(prefixes)}{body}"


def _news_article(body: str) -> str:
    prefixes = [
        "BREAKING:", "THREAT INTEL REPORT:", "INCIDENT UPDATE:", "ADVISORY:",
        "Security researchers report:", "According to analysts:",
    ]
    return f"{random.choice(prefixes)} {body}"


def _chat_log(body: str) -> str:
    handle = random.choice(DARK_WEB_HANDLES)
    return f"<{handle}> {body}"


_STYLES = [_forum_post, _paste_dump, _news_article, _chat_log]


def _style(body: str) -> str:
    return random.choice(_STYLES)(body)


# ── CRITICAL sample generators ─────────────────────────────────────────────────

def _critical_credential_dump() -> Tuple[str, List]:
    actor = random.choice(ACTORS)
    org   = random.choice(ORGS)
    pw    = random.choice(SAMPLE_PASSWORDS)
    count = random.randint(500, 500_000)
    ip    = random.choice(SAMPLE_IPS)
    body  = random.choice([
        f"{actor} dumped credentials from {org}. {count} accounts exposed. "
        f"admin password: {pw}. DB host: {ip}",
        f"Full database dump of {org}. Contains plaintext passwords and API keys. "
        f"root:{pw} SSH access confirmed. Total records: {count:,}",
        f"Leaked: {org} internal credentials. db_pass={pw!r}, admin hash "
        f"{random.choice(SAMPLE_HASHES)}. {count} employees affected.",
        f"CRITICAL LEAK — {org} secret key exposed. access_token and private_key "
        f"in attached archive. Verified by {random.choice(DARK_WEB_HANDLES)}.",
        f"Data breach confirmed at {org}. Stolen files contain password, admin login, "
        f"db_pass for {random.choice(SAMPLE_DOMAINS)}. seller: {actor}",
    ])
    return _style(body), [{"text": actor, "type": "ORG"}, {"text": org, "type": "ORG"}]


def _critical_ransomware_victim() -> Tuple[str, List]:
    actor = random.choice(ACTORS)
    org   = random.choice(ORGS)
    btc   = round(random.uniform(10, 500), 2)
    body  = random.choice([
        f"{actor} has fully encrypted {org}. Ransom demand: {btc} BTC. "
        f"Backdoor planted on {random.choice(SAMPLE_IPS)}. Admin credentials compromised.",
        f"RANSOMWARE ATTACK — {org} systems locked by {actor}. "
        f"All backups wiped. secret decryption key held for ransom.",
        f"{actor} published 50GB of leaked data from {org} on their shame site. "
        f"Files include admin credentials, confidential contracts.",
        f"Negotiation logs: {actor} demanded {btc} BTC from {org}. "
        f"Proof: db_pass and master_key in sample files shared publicly.",
    ])
    return _style(body), [{"text": actor, "type": "ORG"}, {"text": org, "type": "ORG"}]


def _critical_active_exfil() -> Tuple[str, List]:
    actor  = random.choice(ACTORS)
    org    = random.choice(ORGS)
    domain = random.choice(SAMPLE_DOMAINS)
    ip     = random.choice(SAMPLE_IPS)
    body   = random.choice([
        f"ACTIVE EXFIL: {actor} maintaining access to {org} via backdoor on {ip}. "
        f"Dumping Active Directory secrets. admin:password hash cracked.",
        f"Selling access to {org} domain admin. credentials leaked verified. "
        f"RDP open on {ip}. Price: negotiable. Contact: {random.choice(DARK_WEB_HANDLES)}",
        f"{org} {domain} fully compromised. {actor} has root access + VPN credentials. "
        f"All admin passwords rotated to {random.choice(SAMPLE_PASSWORDS)} by attacker.",
    ])
    return _style(body), [{"text": actor, "type": "ORG"}, {"text": org, "type": "ORG"}]


_CRITICAL_GENERATORS = [
    _critical_credential_dump,
    _critical_ransomware_victim,
    _critical_active_exfil,
]


# ── HIGH sample generators ─────────────────────────────────────────────────────

def _high_exploit_release() -> Tuple[str, List]:
    cve  = random.choice(CVE_IDS)
    tech = random.choice(TECHNOLOGIES)
    body = random.choice([
        f"Working exploit for {cve} ({tech}) released. Allows unauthenticated RCE. "
        f"PoC confirmed in the wild. Patch immediately.",
        f"Zero-day exploit published for {tech}. {cve} allows full system bypass. "
        f"Shellcode payload attached. No patch available.",
        f"Exploitation tutorial for {cve} in {tech}: step-by-step lateral movement "
        f"and persistence mechanism. PoC shellcode included.",
        f"New zero-day for {tech} targeting government networks. {cve} allows "
        f"privilege escalation without credentials. Active attacks observed.",
    ])
    return _style(body), [{"text": tech, "type": "PRODUCT"}]


def _high_malware_analysis() -> Tuple[str, List]:
    actor = random.choice(ACTORS)
    tech  = random.choice(TECHNOLOGIES)
    body  = random.choice([
        f"Malware analysis: {actor} new ransomware strain targets {tech}. "
        f"Drops persistent backdoor, disables AV, encrypts shares.",
        f"New phishing campaign attributed to {actor}. Payload delivers malware "
        f"via {tech} exploit. 3,000 victims so far.",
        f"Botnet C2 infrastructure discovered. {actor} using {tech} zero-day "
        f"for initial access. Command and control on {random.choice(SAMPLE_IPS)}.",
        f"{actor} ransomware now includes data exfiltration module. {tech} "
        f"vulnerability used for lateral movement before encryption.",
    ])
    return _style(body), [{"text": actor, "type": "ORG"}, {"text": tech, "type": "PRODUCT"}]


def _high_threat_actor_ttps() -> Tuple[str, List]:
    actor   = random.choice(ACTORS)
    country = random.choice(COUNTRIES)
    cve     = random.choice(CVE_IDS)
    body    = random.choice([
        f"TTP report: {actor} ({country}) using {cve} for initial access, "
        f"then deploying Cobalt Strike for lateral movement and persistence.",
        f"THREAT INTEL: {actor} targeting critical infrastructure in {country}. "
        f"Phishing lures + {cve} exploit chain observed. High confidence attribution.",
        f"Researchers detail {actor} attack chain: spear-phishing → {cve} bypass → "
        f"command and control → data exfiltration. Full indicators released.",
        f"{country}-linked {actor} conducting cyber-espionage via {cve}. "
        f"Victims include defense contractors and energy firms.",
    ])
    return _style(body), [{"text": actor, "type": "ORG"}]


_HIGH_GENERATORS = [
    _high_exploit_release,
    _high_malware_analysis,
    _high_threat_actor_ttps,
]


# ── MEDIUM sample generators ───────────────────────────────────────────────────

def _medium_vuln_disclosure() -> Tuple[str, List]:
    tech = random.choice(TECHNOLOGIES)
    cve  = random.choice(CVE_IDS)
    body = random.choice([
        f"Vulnerability disclosure: {cve} in {tech} allows authenticated users "
        f"to escalate privileges. Patch available. CVSS 7.8.",
        f"Security advisory: {tech} affected by {cve}. Update to latest version. "
        f"No active exploitation observed yet.",
        f"Bug bounty report: {cve} in {tech}. Researchers discovered path traversal "
        f"vulnerability. Vendor notified, fix released.",
        f"{tech} security update addresses {cve}. Vulnerability could allow "
        f"unauthorized access to sensitive files in limited scenarios.",
    ])
    return _style(body), [{"text": tech, "type": "PRODUCT"}]


def _medium_security_research() -> Tuple[str, List]:
    tech = random.choice(TECHNOLOGIES)
    body = random.choice([
        f"Security research: penetration test of {tech} reveals misconfigurations "
        f"that could be exploited by an attacker with network access.",
        f"Threat hunt findings: suspicious reconnaissance activity targeting "
        f"{tech} environments. No breach confirmed. Monitoring ongoing.",
        f"Red team engagement report: {tech} deployment lacks MFA, increasing "
        f"attack surface. Vulnerability assessment complete.",
        f"Incident response exercise reveals {tech} audit gaps. "
        f"Security posture improvements recommended.",
    ])
    return _style(body), [{"text": tech, "type": "PRODUCT"}]


def _medium_threat_intelligence_general() -> Tuple[str, List]:
    org   = random.choice(ORGS)
    body  = random.choice([
        f"Threat intelligence update: increased scanning activity against {org} "
        f"infrastructure. Unauthorized access attempts logged.",
        f"Suspicious login attempts from {random.choice(COUNTRIES)} targeting "
        f"{org}. Incident response team engaged.",
        f"Phishing campaign targeting employees of {org}. No confirmed compromise. "
        f"Security awareness training recommended.",
        f"Dark web monitoring alert: {org} mentioned in threat actor forum. "
        f"No data confirmed leaked. Investigating.",
    ])
    return _style(body), [{"text": org, "type": "ORG"}]


_MEDIUM_GENERATORS = [
    _medium_vuln_disclosure,
    _medium_security_research,
    _medium_threat_intelligence_general,
]


# ── LOW sample generators ──────────────────────────────────────────────────────

def _low_benign_news() -> Tuple[str, List]:
    tech = random.choice(TECHNOLOGIES)
    body = random.choice([
        f"New features released in {tech}. Improved performance and stability "
        f"for enterprise deployments. See release notes for details.",
        f"Industry conference next month: {tech} best practices session. "
        f"Register at the official website.",
        f"Blog post: how to configure {tech} for optimal security. "
        f"Step-by-step guide for administrators.",
        f"Webinar recording available: {tech} deployment tips. "
        f"Covers backup, monitoring, and patch management.",
        f"Career opportunity: {tech} administrator wanted at {random.choice(ORGS)}. "
        f"Competitive salary, good benefits.",
    ])
    return body, [{"text": tech, "type": "PRODUCT"}]


def _low_benign_policy() -> Tuple[str, List]:
    body = random.choice([
        "Updated privacy policy effective next quarter. Changes include clearer "
        "data retention rules and new user consent flows.",
        "Annual security awareness training is now open. Complete by end of month. "
        "Topics: phishing recognition, password hygiene, incident reporting.",
        "Reminder: change your passwords every 90 days per company policy. "
        "Use a password manager for best security.",
        "IT announcement: scheduled maintenance window this Saturday 2–4 AM. "
        "Systems will be briefly unavailable.",
        "Quarterly compliance report submitted. All controls passed audit. "
        "Next review scheduled for Q3.",
    ])
    return body, []


def _low_benign_tech_discussion() -> Tuple[str, List]:
    tech = random.choice(TECHNOLOGIES)
    body = random.choice([
        f"Anyone have experience migrating from {tech} to the cloud? "
        f"Looking for best practices and gotchas.",
        f"Documentation question: how do I configure logging in {tech}? "
        f"The official docs are unclear on the retention settings.",
        f"Just passed my {tech} certification exam! "
        f"Happy to share study resources with anyone preparing.",
        f"Performance tuning tips for {tech}: increase buffer pool, "
        f"optimize queries, review index usage. Results: 40% speed improvement.",
    ])
    return body, [{"text": tech, "type": "PRODUCT"}]


_LOW_GENERATORS = [
    _low_benign_news,
    _low_benign_policy,
    _low_benign_tech_discussion,
]


# ── Adversarial: false positives (benign text with risk keywords) ──────────────

def _false_positive_critical_context() -> Tuple[str, str, List]:
    """Benign text that contains critical keywords but in a non-threatening context."""
    body = random.choice([
        "How to PREVENT admin password leaks in your web application: "
        "use bcrypt hashing, never store credentials in plaintext, rotate API keys.",
        "Security training module 3: recognising leaked credentials. "
        "If you receive an email claiming to contain db_pass or secret keys, "
        "do NOT click links. Report to IT security immediately.",
        "Tutorial: resetting admin password in Windows Active Directory "
        "after a locked-out account. Step 1: log into domain controller…",
        "Discussion: what's the best practice for rotating API keys and "
        "access_token values? Our team uses Vault for secret management.",
        "Academic paper abstract: analysis of password strength requirements "
        "across 500 websites. 40% still allow passwords under 8 characters.",
        "CTF writeup: solved the 'leaked credentials' challenge by finding "
        "the hidden db_pass in the source HTML comment.",
    ])
    return body, "LOW", []


def _false_positive_high_context() -> Tuple[str, str, List]:
    """Benign security education content that mentions exploits/malware."""
    tech = random.choice(TECHNOLOGIES)
    body = random.choice([
        f"Blue team guide: detecting ransomware early using {tech} audit logs. "
        f"Look for mass file rename events and shadow copy deletion.",
        f"How defenders can simulate phishing campaigns to test employee awareness. "
        f"Authorized penetration testing methodology for {tech}.",
        f"MITRE ATT&CK framework explained: understanding lateral movement, "
        f"persistence mechanisms, and command and control for defensive purposes.",
        f"Patch management best practice: prioritize CVEs with public exploit code. "
        f"Use vulnerability assessment tools to identify {tech} exposure.",
        f"Incident response playbook: if malware is detected on {tech}, "
        f"isolate the host, preserve memory, and engage threat hunting team.",
    ])
    return body, "MEDIUM", [{"text": tech, "type": "PRODUCT"}]


_FALSE_POSITIVE_GENERATORS = [
    _false_positive_critical_context,
    _false_positive_high_context,
]


# ── Adversarial: false negatives (risky but subtle) ───────────────────────────

def _subtle_critical() -> Tuple[str, List]:
    """High-risk content without obvious credential-dump keywords."""
    org  = random.choice(ORGS)
    ip   = random.choice(SAMPLE_IPS)
    actor = random.choice(ACTORS)
    body = random.choice([
        f"For sale: full shell on {org}. {ip} wide open. "
        f"All AV bypassed. Persistence confirmed. DM for price.",
        f"{actor} has {org} completely owned. "
        f"24/7 access maintained since last month. Everything exfiltrated.",
        f"Domain controller at {ip} — total pwnage. "
        f"Every account's hash extracted. Contact me for the archive.",
        f"Got a fully functional implant running on {org} infra since Q1. "
        f"Logs show zero detection. Open to monetisation offers.",
    ])
    return _style(body), [{"text": actor, "type": "ORG"}, {"text": org, "type": "ORG"}]


def _subtle_high() -> Tuple[str, List]:
    """High-risk exploit/malware discussion using evasive language."""
    tech = random.choice(TECHNOLOGIES)
    cve  = random.choice(CVE_IDS)
    body = random.choice([
        f"The thing I sent you works on {tech} boxes with default config. "
        f"Pop a shell in under 30 seconds. No AV catches it.",
        f"Updated the tool for {cve}. Tested against patched {tech}. "
        f"Still works if the secondary bypass is applied first.",
        f"Shipping the kit tomorrow. Works on all {tech} versions ≤ latest patch. "
        f"Includes full persistence and cleanup scripts.",
        f"Asked in DM but posting here: does the {tech} module handle the "
        f"auth bypass automatically or do I need to set the flag manually?",
    ])
    return _style(body), [{"text": tech, "type": "PRODUCT"}]


_SUBTLE_GENERATORS = {
    "CRITICAL": _subtle_critical,
    "HIGH":     _subtle_high,
}


# ── Dataset assembly ───────────────────────────────────────────────────────────

def generate(num_samples: int = 50_000) -> List[Dict]:
    samples: List[Dict] = []

    # Target distribution (approximate):
    # CRITICAL 12%, HIGH 28%, MEDIUM 35%, LOW 15%, adversarial FP ~10%
    n_crit   = int(num_samples * 0.12)
    n_high   = int(num_samples * 0.28)
    n_medium = int(num_samples * 0.35)
    n_low    = int(num_samples * 0.15)
    n_fp     = int(num_samples * 0.05)   # false-positive benign-with-keywords
    n_subtle = num_samples - n_crit - n_high - n_medium - n_low - n_fp  # subtle risk

    print(f"Generating {n_crit} CRITICAL samples…")
    for _ in range(n_crit):
        gen = random.choice(_CRITICAL_GENERATORS)
        text, entities = gen()
        samples.append({"text": text, "expected_label": "CRITICAL", "entities": entities})

    print(f"Generating {n_high} HIGH samples…")
    for _ in range(n_high):
        gen = random.choice(_HIGH_GENERATORS)
        text, entities = gen()
        samples.append({"text": text, "expected_label": "HIGH", "entities": entities})

    print(f"Generating {n_medium} MEDIUM samples…")
    for _ in range(n_medium):
        gen = random.choice(_MEDIUM_GENERATORS)
        text, entities = gen()
        samples.append({"text": text, "expected_label": "MEDIUM", "entities": entities})

    print(f"Generating {n_low} LOW samples…")
    for _ in range(n_low):
        gen = random.choice(_LOW_GENERATORS)
        text, entities = gen()
        samples.append({"text": text, "expected_label": "LOW", "entities": entities})

    print(f"Generating {n_fp} adversarial false-positive samples…")
    for _ in range(n_fp):
        gen = random.choice(_FALSE_POSITIVE_GENERATORS)
        result = gen()
        text, label, entities = result
        samples.append({"text": text, "expected_label": label, "entities": entities})

    n_subtle_crit = n_subtle // 2
    n_subtle_high = n_subtle - n_subtle_crit
    print(f"Generating {n_subtle} subtle/adversarial risk samples…")
    for _ in range(n_subtle_crit):
        text, entities = _subtle_critical()
        samples.append({"text": text, "expected_label": "CRITICAL", "entities": entities})
    for _ in range(n_subtle_high):
        text, entities = _subtle_high()
        samples.append({"text": text, "expected_label": "HIGH", "entities": entities})

    random.shuffle(samples)
    return samples


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic threat-intel training data")
    parser.add_argument("--n", type=int, default=50_000, help="Total samples to generate")
    args = parser.parse_args()

    samples = generate(args.n)

    output_path = Path(__file__).parent / "evals" / "risk_eval_cases.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(samples, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(samples)} samples → {output_path}")

    label_counts: Dict[str, int] = {}
    for s in samples:
        label_counts[s["expected_label"]] = label_counts.get(s["expected_label"], 0) + 1

    print("\nLabel distribution:")
    for label in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        count = label_counts.get(label, 0)
        pct   = 100 * count / len(samples)
        print(f"  {label:10s}: {count:6d} ({pct:5.1f}%)")


if __name__ == "__main__":
    main()

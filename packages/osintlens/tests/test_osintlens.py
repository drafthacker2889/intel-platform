"""Tests that run on a base (dependency-free) install."""

import osintlens as ol
from osintlens.iocs import extract_iocs
from osintlens.risk import score_rules


def test_iocs_extract_values():
    text = (
        "Contact admin@corp.example or visit https://evil.test/panel. "
        "Host 45.13.2.11, hash 5d41402abc4b2a76b9719d911017c592, "
        "see CVE-2024-1337."
    )
    iocs = extract_iocs(text)
    assert iocs["email"] == ["admin@corp.example"]
    assert iocs["ipv4"] == ["45.13.2.11"]
    assert iocs["url"] == ["https://evil.test/panel."]
    assert iocs["md5"] == ["5d41402abc4b2a76b9719d911017c592"]
    assert iocs["cve"] == ["CVE-2024-1337"]


def test_ipv4_rejects_out_of_range_octets():
    assert extract_iocs("999.999.999.999 is not an ip")["ipv4"] == []


def test_rules_flags_critical():
    text = "Leaked db_pass and admin credentials; login backdoor api_key dump"
    score, label = score_rules(text, entities=[])
    assert label == "CRITICAL"
    assert score >= 50


def test_benign_text_is_low_risk():
    score, label = score_rules("The weather today is pleasant and calm.", entities=[])
    assert label == "LOW"
    assert score == 0


def test_analyze_end_to_end_degraded():
    result = ol.analyze("Leaked db_pass for admin@corp.example, C2 at 45.13.2.11")
    assert result.risk.label == "CRITICAL"
    assert result.risk.backend == "rules"
    assert result.language.code == "en"
    assert "admin@corp.example" in result.iocs["email"]
    # Round-trips to JSON without error.
    assert '"CRITICAL"' in result.to_json()


def test_graph_export_shapes():
    result = ol.analyze("Ransomware C2 at 45.13.2.11 targeting admin accounts")
    graph = result.graph(document_id="doc-1")
    assert any(n["label"] == "Document" for n in graph["nodes"])
    assert all({"from", "to", "type"} <= set(e) for e in graph["edges"])
    assert any(e["type"] == "CONTAINS" for e in graph["edges"])


def test_featurize_vector_length():
    vec = ol.featurize("password leak", entities=[])
    assert len(vec) == len(ol.FEATURE_NAMES) == 12

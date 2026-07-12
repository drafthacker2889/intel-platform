"""Tests for synthreat (pure-Python, no extras needed)."""

import json

import pytest

import synthreat
from synthreat import ThreatDataGenerator


def test_reproducible_with_seed():
    a = synthreat.generate(samples_per_language=50, seed=123).to_list()
    b = synthreat.generate(samples_per_language=50, seed=123).to_list()
    assert a == b


def test_different_seeds_differ():
    a = synthreat.generate(samples_per_language=50, seed=1).to_list()
    b = synthreat.generate(samples_per_language=50, seed=2).to_list()
    assert a != b


def test_exact_total_and_languages():
    ds = synthreat.generate(samples_per_language=100, seed=7)
    assert len(ds) == 400  # 4 languages * 100
    assert set(ds.stats()["by_language"]) == set(synthreat.LANGUAGES)
    assert set(ds.stats()["by_label"]) == set(synthreat.LABELS)


def test_language_subset():
    ds = synthreat.generate(samples_per_language=25, seed=7, languages=["en", "ru"])
    assert set(ds.stats()["by_language"]) == {"en", "ru"}
    assert len(ds) == 50


def test_custom_distribution_hits_exact_total():
    gen = ThreatDataGenerator(seed=0, languages=["en"])
    ds = gen.generate(
        samples_per_language=200,
        distribution={"CRITICAL": 0.25, "HIGH": 0.25, "MEDIUM": 0.25, "LOW": 0.25},
    )
    assert len(ds) == 200
    counts = ds.stats()["by_label"]
    assert counts["CRITICAL"] == 50 and counts["LOW"] == 50


def test_ioc_injection_records_ground_truth():
    ds = synthreat.generate(samples_per_language=100, seed=9, inject_iocs=1.0)
    for sample in ds:
        assert sample.iocs, "every sample should carry IOCs at inject_iocs=1.0"
        # The recorded indicators must actually appear in the text.
        assert sample.iocs["ipv4"][0] in sample.text
        assert sample.iocs["email"][0] in sample.text
        assert sample.iocs["cve"][0] in sample.text


def test_no_injection_by_default():
    ds = synthreat.generate(samples_per_language=50, seed=9)
    assert all(not s.iocs for s in ds)


def test_training_data_shape_for_osintlens():
    ds = synthreat.generate(samples_per_language=10, seed=3)
    cases = ds.as_training_data()
    assert all({"text", "entities", "expected_label"} <= set(c) for c in cases)


def test_jsonl_round_trips():
    ds = synthreat.generate(samples_per_language=10, seed=3)
    lines = ds.to_jsonl().splitlines()
    assert len(lines) == len(ds)
    assert all(json.loads(line)["label"] in synthreat.LABELS for line in lines)


def test_rejects_bad_inputs():
    with pytest.raises(ValueError):
        ThreatDataGenerator(languages=["xx"])
    with pytest.raises(ValueError):
        ThreatDataGenerator(inject_iocs=1.5)


def test_save_infers_format(tmp_path):
    ds = synthreat.generate(samples_per_language=5, seed=1)
    jsonl = ds.save(tmp_path / "out.jsonl")
    assert len(jsonl.read_text(encoding="utf-8").splitlines()) == len(ds)
    js = ds.save(tmp_path / "out.json")
    assert isinstance(json.loads(js.read_text(encoding="utf-8")), list)

# synthreat

**Reproducible synthetic threat-intelligence datasets — in four languages.**

Labeled multilingual security-text corpora barely exist. `synthreat` generates
them on demand: threat-intel sentences in **English, Russian, Chinese, and
German**, each tagged with a risk label (`CRITICAL` / `HIGH` / `MEDIUM` /
`LOW`), named entities, and — optionally — **ground-truth indicators of
compromise**. Seed it and the output is byte-for-byte reproducible.

```python
import synthreat

ds = synthreat.generate(samples_per_language=1000, seed=42, inject_iocs=0.3)

len(ds)            # 4000
ds.stats()         # {'by_language': {...}, 'by_label': {...}, 'with_iocs': ~1200}
ds.save("threats.jsonl")
```

Zero runtime dependencies — pure Python.

```bash
pip install synthreat
```

## Why it's different

Most synthetic-data tools are generic (`faker`, `mimesis`) and know nothing
about security text. `synthreat` is purpose-built for threat intelligence, and
it's **multilingual by construction** — not English translated after the fact.
Because injected IOCs are known at generation time, every enriched sample
carries its indicators as ground truth, so the same dataset benchmarks **both**
a risk classifier *and* an IOC extractor.

## Ground-truth IOCs

With `inject_iocs`, a fraction of samples get a synthetic IP / email / SHA-256 /
CVE embedded in the text and recorded on the sample:

```python
ds = synthreat.generate(samples_per_language=10, seed=1, inject_iocs=1.0)
s = ds[0]
s.text          # "...LEAKED... Contact admin@example.com; C2 at 192.0.2.77; sample 9f...; ref CVE-2021-4242."
s.iocs          # {'ipv4': ['192.0.2.77'], 'email': ['admin@example.com'], 'sha256': ['9f...'], 'cve': ['CVE-2021-4242']}
```

Every value is synthetic and safe: IPs come from RFC 5737 documentation ranges
and domains from RFC 2606 reserved names, so nothing resolves to a real host.

## Pairs with [osintlens](https://pypi.org/project/osintlens/)

`synthreat` produces training/eval data in the exact shape `osintlens` consumes:

```python
from synthreat import generate
from osintlens.ml import train

ds = generate(samples_per_language=2000, seed=0)
train(ds.as_training_data(), output_path="risk_model.joblib")
```

And with IOC injection you can measure extractor recall directly, comparing
`osintlens.extract_iocs(sample.text)` against `sample.iocs`.

## Customize

```python
from synthreat import ThreatDataGenerator

gen = ThreatDataGenerator(
    seed=7,
    languages=["en", "de"],
    inject_iocs=0.5,
    vocab_overrides={"ACTORS": {"en": ["MyActor"], "de": ["MeinAkteur"]}},
)
ds = gen.generate(
    samples_per_language=500,
    distribution={"CRITICAL": 0.25, "HIGH": 0.25, "MEDIUM": 0.25, "LOW": 0.25},
)
```

## Command line

```bash
synthreat generate -n 5000 --seed 42 -o threats.jsonl
synthreat generate -n 100 --languages en ru --inject-iocs 0.4 --format json
cat <(synthreat generate -n 10 --seed 1)   # prints JSON to stdout
```

## Output schema

Each sample:

```json
{
  "text": "LEAKED: database dump - Fortune 500 company admin credentials exposed",
  "label": "CRITICAL",
  "language": "en",
  "entities": [{"text": "LockBit", "type": "ORG"}, {"text": "Fortune 500 company", "type": "ORG"}],
  "iocs": {}
}
```

## A note on use

The data is fabricated for training, testing, and benchmarking. It is not real
intelligence and should never be presented as genuine threat reporting.

## Author

Created and maintained by **muhammed shazin sadhik kunhi parambath**.

## License

MIT

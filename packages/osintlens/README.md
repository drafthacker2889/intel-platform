# osintlens

**Multilingual OSINT analysis in a single call.** Point it at a block of text —
a forum post, a paste, a scraped page — and get back the language, the
indicators of compromise, the named entities, and an explainable risk verdict.

```python
import osintlens as ol

result = ol.analyze("Leaked db_pass for admin@corp.example, C2 at 45.13.2.11")

result.risk.label          # 'CRITICAL'
result.risk.confidence     # 95
result.language.code       # 'en'
result.iocs["email"]       # ['admin@corp.example']
result.iocs["ipv4"]        # ['45.13.2.11']
result.matched_keywords    # {'critical': ['db_pass', ...], 'high': ['c2'], ...}
```

Most OSINT tooling on PyPI does *one* of these things — `iocextract` pulls
indicators, a separate library detects language, another scores risk. `osintlens`
runs the whole triage pipeline in one call, and it does it across **English,
Russian, Chinese, and German** text, not just English.

## Install

The base install is **pure Python with zero dependencies** — rule-based risk
scoring and IOC extraction work out of the box:

```bash
pip install osintlens
```

Add optional backends only when you need them:

```bash
pip install "osintlens[multilingual]"   # fine-grained langdetect + spaCy NER
pip install "osintlens[ml]"             # scikit-learn risk model
pip install "osintlens[all]"            # everything
```

Everything degrades gracefully. Without `[multilingual]`, language detection
falls back to a Unicode-script heuristic (still distinguishes ru/zh from
Latin) and entity extraction returns an empty list — IOCs act as a
dependency-free entity floor. Without `[ml]`, risk scoring uses the rule
engine. Nothing crashes because an extra is missing.

For spaCy NER you also need the language models, e.g.:

```bash
python -m spacy download en_core_web_sm
```

## What you get back

`analyze()` returns an `AnalysisResult`:

| Field | Description |
|-------|-------------|
| `language` | `code`, `name`, `confidence`, `supported` |
| `risk` | `label` (LOW/MEDIUM/HIGH/CRITICAL), `score`, `confidence`, `backend` |
| `iocs` | dict of `ipv4`, `email`, `url`, `md5`, `sha1`, `sha256`, `cve`, `btc` |
| `entities` | list of `{text, type, start, end, language}` (needs `[multilingual]`) |
| `matched_keywords` | risk keywords found, grouped by tier |
| `text_sha256` | content hash for dedup / provenance |

`result.to_json()` serializes the whole thing.

## Build a knowledge graph

Every result can emit graph-ready nodes and edges, so you can knit many
documents into a shared Neo4j (or any property-graph) view — the same entity
seen in two documents becomes one shared node:

```python
graph = result.graph(document_id="post-42")
# {"nodes": [{"id": "Document"...}, {"id": "email:admin@corp.example"...}],
#  "edges": [{"from": "post-42", "to": "email:...", "type": "CONTAINS"}]}
```

## Command line

```bash
osintlens scan report.txt                 # analyze a file, print JSON
cat paste.txt | osintlens scan -           # read stdin
osintlens scan report.txt --graph post-42  # emit graph nodes/edges
osintlens scan report.txt --ml-model risk_model.joblib
```

## Train your own risk model

```python
from osintlens.ml import train

train(labeled_cases, output_path="risk_model.joblib")
# labeled_cases: [{"text": ..., "entities": [...], "expected_label": "HIGH"}, ...]
```

The model learns over the 12-element feature vector from `osintlens.featurize`,
so it's a drop-in replacement for the rule engine via
`Analyzer(ml_model_path="risk_model.joblib")`.

## Responsible use

`osintlens` analyzes text you already have. It does not fetch, scrape, or route
traffic, and it is intended for defensive threat intelligence, security
research, and authorized OSINT. Respect the terms of service and applicable law
for any source you collect from, and don't use it to profile or target private
individuals.

## Author

Created and maintained by **muhammed shazin sadhik kunhi parambath**.

## License

MIT

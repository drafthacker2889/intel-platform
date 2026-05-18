# Complete Production Threat Intelligence Crawler Upgrade

## Overview
Transform intel-platform from a prototype into a production-grade threat intelligence system supporting:
- JavaScript-rendered pages (Playwright headless browser)
- CAPTCHA automatic solving (2Captcha + Tesseract OCR fallback)
- Persistent content deduplication (SHA-256 hashing)
- Multilingual support (spaCy + mBERT)
- Entity relationship graph (Neo4j integration)
- Synthetic ML training data (10K+ labeled samples)
- Distributed crawling (multiple instances)
- Elasticsearch clustering
- Dark web (.onion) + clearnet crawling

## Phase 1: Core Crawler Redesign (Priority 1)

### 1.1 Replace Collector-Go with Collector-Python
**Why Python?**
- Native Playwright support (better than rod/colly)
- Easy CAPTCHA integration (pytesseract, 2captcha-python)
- Shares ML/NLP infrastructure with brain-python
- Better async/await for distributed crawling

**New Architecture:**
```
collector-python/
├── src/
│   ├── main.py              # Entry point, queue processing
│   ├── crawler.py           # Playwright-based web crawler
│   ├── captcha_solver.py    # CAPTCHA detection + solving
│   ├── dedup.py             # Redis-based content dedup
│   ├── tor.py               # Tor circuit management
│   └── extractor.py         # Link extraction from rendered pages
├── requirements.txt
├── Dockerfile
└── tests/
    └── test_crawler.py
```

### 1.2 Key Features
1. **Playwright rendering** — handles JS, SPAs, dynamic content
2. **Tor + circuit rotation** — new circuit every 10 pages
3. **Persistent dedup** — Redis + SHA-256 prevents duplicate indexing
4. **CAPTCHA solver** — 2Captcha API with Tesseract OCR fallback
5. **Clearnet + .onion** — unified crawler for both
6. **Session management** — cookie jar per domain
7. **Metrics** — pages crawled, CAPTCHAs hit, dupes rejected

## Phase 2: ML Model Enhancement (Priority 2)

### 2.1 Synthetic Dataset Generator
**Create 10,000 labeled training samples** covering:
- Data breaches (database dumps, password lists)
- Credential leaks (emails+passwords, API keys)
- Threat actor activity (forum posts, market listings)
- Malware analysis (technical writeups)
- Vulnerability disclosures
- Phishing campaigns

**Generation strategy:**
- Template-based: combine real + synthetic phrases
- Keyword injection: insert risk keywords into neutral text
- NER augmentation: add fake entity mentions
- Multilingual: translate to Russian, Chinese, German

### 2.2 Multilingual Support
- Replace spaCy en_core_web_sm with multilingual model (mBERT)
- Language detection on every document (langdetect)
- Per-language keyword lists
- Elasticsearch analyzer per language

### 2.3 Enhanced Model
- Feature engineering from synthetic data
- Cross-validation on stratified splits
- Hyperparameter tuning (grid search)
- SHAP values for explainability
- Fallback to rule-based if model confidence < 0.6

## Phase 3: Neo4j Entity Graph (Priority 3)

### 3.1 Graph Schema
```
Entity nodes: Person, Organization, Location, IPAddress, Domain, EmailAddress
Relationships:
  - MENTIONED_IN (Entity -> Document)
  - CO_OCCURS (Entity -> Entity, weight based on frequency)
  - BELONGS_TO (Domain -> Organization)
  - OWNED_BY (EmailAddress -> Organization)
  - POSTED_BY (Document -> Actor)
```

### 3.2 Brain-Python Integration
- Write extracted entities to Neo4j after Elasticsearch indexing
- Build co-occurrence relationships
- Store entity first-seen, last-seen timestamps

## Phase 4: Deduplication & Scale (Priority 4)

### 4.1 Content Deduplication
- SHA-256(cleaned_text) → Redis set: dedup_hashes
- SHA-256(url) → Redis set: crawled_urls
- Persistent across restarts (persisted to disk)
- TTL: 90 days

### 4.2 Elasticsearch Clustering
- Recommended: 3-node cluster, 1 replica minimum
- Index shards: 5 (for parallelism)
- ILM rollover: daily indices

### 4.3 Distributed Crawling
- Multiple collector instances (config: MAX_INSTANCES=5)
- Redis queue balances work
- Each instance tracks its own visited URLs in-memory (dedup in brain-python catches cross-instance dupes)

## Implementation Timeline

| Phase | Days | Dependencies |
|-------|------|--------------|
| 1. Crawler rewrite (Python + Playwright + CAPTCHA) | 2-3 | Docker, playwright, 2captcha |
| 2. Synthetic data + multilingual | 1-2 | scikit-learn, langdetect, mBERT |
| 3. Neo4j graph layer | 1 | py2neo |
| 4. Scale + dedup refinement | 1 | redis cluster guide |
| **Total** | **5-7** | |

## Success Criteria

- ✅ Crawler handles JS-rendered sites (Playwright)
- ✅ CAPTCHA auto-solved in <30s
- ✅ Zero duplicate documents in Elasticsearch (content hash check)
- ✅ Neo4j has entity graph with 1000+ co-occurrence edges
- ✅ ML model trained on 10K synthetic samples, >85% test accuracy
- ✅ Multilingual: processes Russian, Chinese, German documents
- ✅ Multiple crawlers running without contention
- ✅ Production-ready deployment guide included

---

**Status:** Ready to commence Phase 1

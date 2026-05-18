# Production ML System Architecture

This document describes the upgraded intel-platform architecture for production dark web + clearnet crawling with robust ML risk classification.

## Overview

The system is a multi-stage intelligent data pipeline:

```
Raw Content (HTTP/HTTPS) 
    ↓ (collector-python/collector-go)
Redis Queue: raw_html
    ↓ (sanitizer-rust)
Redis Queue: sanitized_text
    ↓ (brain-python)
[Elasticsearch + Neo4j + Metrics]
    ↓ (dashboard-ui)
[Web UI / APIs]
```

## Phase 1: Production-Grade Python Crawler (collector-python)

### Architecture

**collector-python** is a JavaScript-capable async web crawler built with Playwright for rendering JavaScript and handling modern web applications.

#### Key Features

1. **Multi-Worker Async Crawling**
   - Configurable worker count (default 5)
   - Async/await pattern for I/O efficiency
   - Queue-based task distribution

2. **JavaScript Rendering**
   - Playwright Chromium browser for rendering
   - Automatic page loading and waiting
   - JavaScript execution for dynamic content
   - Screenshot capability for debugging

3. **Tor Integration**
   - SOCKS5 proxy routing through Tor
   - Automatic circuit rotation (every 10 pages)
   - Control port integration for new circuits
   - Circuit validation on failure

4. **CAPTCHA Handling**
   - Automatic CAPTCHA detection
   - 2Captcha API integration (reCAPTCHA v2, hCaptcha)
   - Tesseract OCR fallback for image-based CAPTCHAs
   - Exponential backoff on CAPTCHA solve failures

5. **Persistent Content Deduplication**
   - SHA-256 content hashing
   - Redis-backed storage (90-day TTL)
   - URL deduplication before crawling
   - Prevents duplicate indexing across crawl sessions

6. **Link Extraction & Filtering**
   - BeautifulSoup-based DOM parsing
   - Automatic relative URL resolution
   - Allowed domain filtering (whitelist support)
   - Unwanted file type filtering (.pdf, .exe, .jpg, .mp4, etc.)
   - Tracking parameter removal (utm_*, fbclid, gclid)

7. **Metrics & Health**
   - Prometheus-compatible /metrics endpoint
   - HTTP /health endpoint for orchestration
   - Counter: pages_crawled, links_discovered, captcha_solved, dedup_hits
   - Gauge: active_workers, circuit_rotation_count

#### File Structure

```
services/collector-python/
├── Dockerfile
├── .dockerignore
├── requirements.txt
└── src/
    ├── main.py              # Entry point, Config, Redis, Tor, Dedup init
    ├── crawler.py           # PlaywrightCrawler class (269 lines)
    ├── captcha_solver.py    # 2Captcha + Tesseract solver (192 lines)
    ├── dedup.py             # Redis dedup manager (48 lines)
    ├── tor.py               # Tor circuit rotation
    ├── extractor.py         # Link extraction & filtering
    └── health.py            # Health endpoint handler (if split out)
```

#### Configuration

Environment variables (see .env.example):

```bash
REDIS_HOST=redis              # Queue backend
REDIS_PORT=6379
REDIS_PASSWORD=               # Must match redis service
TOR_PROXY=socks5://tor-proxy:9050
START_URL=https://...         # Initial crawl URL
ALLOWED_DOMAINS=...           # Comma-separated whitelist
SANITIZED_QUEUE_NAME=raw_html # Output queue
PLAYWRIGHT_TIMEOUT_MS=30000   # Page load timeout
CAPTCHA_SOLVER_ENABLED=true   # Enable auto CAPTCHA solving
CAPTCHA_2_KEY=                # 2Captcha API key (if solver enabled)
```

#### Docker Compose Integration

```yaml
collector-python:
  build:
    context: ./services/collector-python
  environment:
    - REDIS_HOST=redis
    - TOR_PROXY=socks5://tor-proxy:9050
    - START_URL=${START_URL}
    - CAPTCHA_2_KEY=${CAPTCHA_2_KEY}
  depends_on:
    - redis (service_healthy)
    - tor-proxy (service_healthy)
  mem_limit: 1g
  cpus: "1.0"
  healthcheck:
    test: ["CMD-SHELL", "wget -qO- http://localhost:8081/health >/dev/null"]
```

#### Running

```bash
# Build
docker compose build collector-python

# Start (assumes redis + tor-proxy already running)
docker compose up collector-python -d

# Check logs
docker logs intel_collector_py

# Monitor metrics
curl http://localhost:8081/metrics

# Health check
curl http://localhost:8081/health
```

## Phase 2: Synthetic ML Training Data

### Approach

Production-grade ML models require labeled datasets. **generate_synthetic_data.py** creates 10,000+ realistic threat intelligence samples with labels (CRITICAL/HIGH/MEDIUM/LOW) for training.

### Distribution

```
10% (1,000)   CRITICAL - Credential leaks, active breaches, database dumps
30% (3,000)   HIGH     - Exploits, zero-days, malware, RATs, phishing
40% (4,000)   MEDIUM   - Security research, incident response, threat hunts
20% (2,000)   LOW      - General news, events, documentation
```

### Template Examples

**CRITICAL samples:**
```
"LockBit leaked database dump of Fortune 500 company: admin password is... for 125 employees"
"LEAKED: db_password - healthcare provider admin credentials exposed in dark web"
"Active directory backup found in ransomware dump by Lazarus Group"
```

**HIGH samples:**
```
"Zero day information - Cisco ASA flaw exploited by APT28 in the wild"
"New exploitation tutorial targeting Windows Server vulnerabilities"
"Malware analysis report: Banking trojan new variant with persistence mechanisms"
```

### Named Entities

- **Actors**: LockBit, Royal, BlackCat, Lazarus Group, APT28, etc.
- **Organizations**: Fortune 500, healthcare, financial, government, tech, university
- **Technologies**: Windows Server, Linux, Apache, MySQL, Active Directory, Exchange, FortiGate

### Usage

```bash
cd services/brain-python

# Generate 10,000 samples
python generate_synthetic_data.py

# Output: evals/risk_eval_cases.json (2.5MB JSON)
# Format: [{"text": "...", "expected_label": "CRITICAL", "entities": [...]}, ...]
```

### Integration with train_risk_model.py

```bash
# Train RandomForest on synthetic data
python train_risk_model.py

# Output: models/risk_model.joblib
# Includes:
#   - 80/20 train/test split with stratification
#   - Cross-validation (k-fold, k=min(min_class_count, 3))
#   - Classification report (precision, recall, F1)
#   - Feature importances for explainability
```

## Phase 3: Entity Relationship Graph (Neo4j)

### Purpose

Transforms individual documents into a knowledge graph of entities and relationships. Enables:

- Finding compromised organizations
- Tracking threat actors and their targets
- Discovering entity co-occurrences
- Analyzing incident timelines

### Schema

**Nodes:**
```
Person        {text: "John Smith", created_at, last_seen}
Organization  {text: "Acme Corp", created_at, last_seen}
Location      {text: "US", created_at, last_seen}
EmailAddress  {text: "admin@example.com", created_at, last_seen}
Domain        {text: "example.com", created_at, last_seen}
IPAddress     {text: "192.0.2.1", created_at, last_seen}
Document      {id, url, risk_label, indexed_at}
```

**Relationships:**
```
MENTIONED_IN  {source: Entity, target: Document}  # Entity appears in document
CO_OCCURS     {source: Entity, target: Entity, count: N}  # Entity co-occurrence
BELONGS_TO    {source: Entity, target: Organization}  # e.g., Email belongs to Org
```

### Integration

**brain-python/src/neo4j_manager.py** (NEW):

```python
# After successful ES indexing:
neo4j_mgr.ingest_document(
    doc_id="uuid",
    entities=[{"text": "LockBit", "type": "ORG"}, ...],
    source_url="...",
    risk_label="CRITICAL"
)

# Automatically:
#   1. Creates entity nodes (or matches existing)
#   2. Creates MENTIONED_IN edges
#   3. Creates CO_OCCURS edges between entity pairs
```

### Queries

```cypher
# Find all entities mentioned with a specific actor
MATCH (actor:ORG {text: "LockBit"})
MATCH (entity)-[:CO_OCCURS]-(actor)
RETURN entity, actor

# Timeline of incidents mentioning an organization
MATCH (org:Organization {text: "Target Corp"})
MATCH (org)<-[:MENTIONED_IN]-(doc:Document)
RETURN doc.url, doc.indexed_at, doc.risk_label
ORDER BY doc.indexed_at DESC
```

### Configuration

Docker compose env vars:

```yaml
brain-python:
  environment:
    - NEO4J_URI=neo4j://neo4j:7687
    - NEO4J_USER=neo4j
    - NEO4J_PASSWORD=${NEO4J_PASSWORD}
  depends_on:
    - neo4j (service_healthy)
```

## Phase 4: Production Scale-Out (TBD)

### Elasticsearch Clustering

- 3+ nodes with voting_only + data node roles
- Index Lifecycle Management (ILM) for time-based retention
- Replication factor ≥ 1 for fault tolerance
- Shard allocation awareness by zone

### Redis Clustering

- 3+ master nodes + 3+ replica nodes
- Automatic failover via Sentinel or Cluster protocol
- Persistent storage (AOF + RDB)
- Cross-dc replication for disaster recovery

### Multi-Instance Crawling

- Multiple collector-python instances reading from shared queue
- Load-balanced via Redis BLPOP
- Shared dedup store (Postgres or external Redis)
- Tor circuit rotation per-instance

## Deployment

### Development (docker-compose.yml)

```bash
docker-compose up
# Full stack with all services
```

### Observability (docker-compose.observability.yml)

```bash
docker-compose -f docker-compose.observability.yml up
# Prometheus + Grafana + Tempo + OTEL Collector
```

### Production (docker-compose.prod.yml)

```bash
docker-compose -f docker-compose.prod.yml up
# Security hardening: Elasticsearch auth, no debug ports
```

## Metrics & Monitoring

### Prometheus Scrapes

```
# collector-python
POST http://localhost:8081/metrics
  pages_crawled_total
  links_discovered_total
  captcha_solved_total
  dedup_hits_total
  active_workers

# brain-python
POST http://localhost:8082/metrics
  documents_processed_total
  index_failures_total
  risk_score_histogram

# sanitizer-rust
POST http://localhost:8083/metrics
  documents_sanitized_total
  extraction_errors_total
```

### Grafana Dashboards

- Crawler throughput (pages/min, links/min)
- CAPTCHA solve rate
- Dedup hit rate
- ML model prediction distribution
- Elasticsearch indexing latency
- Pipeline end-to-end latency

## Testing

### Integration Test (tests/integration/test_pipeline.sh)

```bash
./tests/integration/test_pipeline.sh

# Validates full flow:
# 1. synthetic payload → sanitizer-rust
# 2. → brain-python
# 3. → elasticsearch (verify risk_label, entities)
```

### Unit Tests

```bash
# brain-python
cd services/brain-python && python -m pytest src/test_main.py -v

# auth-api
cd services/auth-api && python -m pytest src/test_main.py -v

# collector-go
cd services/collector-go && go test ./...

# sanitizer-rust
cd services/sanitizer-rust && cargo test --locked
```

## Troubleshooting

### Crawler stuck on CAPTCHA

```bash
# Check 2Captcha API key validity
curl https://2captcha.com/api/user?key=YOUR_KEY&action=userinfo

# Check Tor connection
curl --socks5 localhost:9050 -I https://icanhazip.com
```

### Brain health showing failures

```bash
# Check Elasticsearch connectivity
curl http://localhost:9200/_cluster/health

# Check Neo4j connectivity
curl -u neo4j:password http://localhost:7474/browser

# Monitor brain logs
docker logs intel_brain | grep -i error
```

### Redis queue growth

```bash
# Check queue depth
redis-cli -a PASSWORD LLEN raw_html
redis-cli -a PASSWORD LLEN sanitized_text

# Drain DLQ to investigate failures
redis-cli -a PASSWORD LPOP raw_html_dlq | jq .
```

## References

- [Playwright Docs](https://playwright.dev/python/)
- [2Captcha API](https://2captcha.com/api)
- [Neo4j Cypher](https://neo4j.com/docs/cypher-manual/)
- [Elasticsearch](https://www.elastic.co/guide/en/elasticsearch/reference/current/)
- [Prometheus](https://prometheus.io/docs/)

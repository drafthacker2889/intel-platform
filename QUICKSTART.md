# Quick Start: Production ML System

## Prerequisites

- Docker & Docker Compose installed
- 2Captcha API key (optional, for CAPTCHA handling)
- Minimum 4GB RAM available for containers

## Step 1: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with real values:

```bash
# Critical
AUTH_SECRET_KEY=your_min_32_char_secret_here_abc123
ELASTIC_PASSWORD=strong_elastic_password
NEO4J_PASSWORD=strong_neo4j_password
REDIS_PASSWORD=strong_redis_password

# Optional but recommended
CAPTCHA_2_KEY=your_2captcha_api_key
CAPTCHA_SOLVER_ENABLED=true

# Crawler
START_URL=https://www.torproject.org
ALLOWED_DOMAINS=www.torproject.org,support.torproject.org
```

## Step 2: Generate ML Training Data

Generate synthetic datasets in English and multiple languages:

```bash
cd services/brain-python

# Generate English synthetic data (10K samples)
python generate_synthetic_data.py

# Generate multilingual synthetic data (30K samples, 4 languages: en/ru/zh/de)
python generate_multilingual_data.py
```

**Output:**
- `evals/risk_eval_cases.json` — 10K English samples
- `evals/multilingual_eval_cases.json` — 30K multilingual samples
- Total: 40K labeled threat intelligence samples

## Step 3: Train ML Model

Train an advanced RandomForest model on both English and multilingual synthetic data:

```bash
# Train advanced model (combines both datasets + augmentation)
python train_advanced_model.py

# Output: 
#   - models/risk_model_advanced.joblib (advanced model with metrics)
#   - models/risk_model.joblib (compatibility model)
#   - models/scaler.pkl (feature scaler)

# See docs/MODEL_TRAINING.md for training details, metrics, and tuning
cd ../..
```

**Expected output:**
- Test accuracy: 88-92%
- F1-weighted score: 0.87-0.91
- Per-class precision/recall/F1 breakdown
- Feature importance analysis

## Step 4: Build All Images

```bash
docker compose build
```

This builds:
- elasticsearch, kibana, neo4j, redis, tor-proxy
- collector-go, collector-python, sanitizer-rust, brain-python, auth-api, dashboard-ui

## Step 5: Start Development Stack

```bash
docker compose up -d
```

Wait for services to become healthy (~60 seconds):

```bash
docker compose ps
# All services should show "healthy" in STATUS column
```

## Step 6: Verify Pipeline

### Option A: Using integration test

```bash
bash tests/integration/test_pipeline.sh
```

Expected output:
```
✓ Elasticsearch healthy
✓ Brain ready
✓ Test payload indexed
✓ Risk label verified as HIGH/CRITICAL
```

### Option B: Manual verification

```bash
# Check collector-python logs
docker logs intel_collector_py

# Check crawler is running
curl http://localhost:8081/health
# {"status": "crawling", "pages_crawled": 42, ...}

# Check brain processing
curl http://localhost:8082/health
# {"status": "ready", "documents_processed": 128, ...}

# Check Elasticsearch
curl http://localhost:9200/_cluster/health
# {"status": "green", "active_shards": 5, ...}

# Check Neo4j
curl -u neo4j:yourpassword http://localhost:7474/browser
```

## Step 7: Access Dashboards

- **Kibana** (Elasticsearch): http://localhost:5601
- **Neo4j Browser**: http://localhost:7474 (default: neo4j/password)
- **Dashboard UI**: http://localhost:3000
- **Prometheus**: http://localhost:9090 (if observability stack running)

## Step 8: Monitor Pipeline

```bash
# Watch brain-python process documents
docker logs -f intel_brain | grep -E "processed|risk_label|entities"

# Check queue depth
docker exec intel_queue redis-cli -a $REDIS_PASSWORD LLEN sanitized_text

# Monitor Elasticsearch index
curl http://localhost:9200/intel-data-v3/_stats | jq '.indices[] | .primaries'
```

## Step 9: Stop Services

```bash
docker compose down
```

## Troubleshooting

### Crawler not producing data

```bash
# Check Tor connection
docker logs intel_tor | tail -20

# Check collector-python connectivity to Tor
curl --socks5 localhost:9050 -I https://icanhazip.com

# Manual verify with verbose logging
docker exec intel_collector_py python -c "from src.crawler import PlaywrightCrawler; ..."
```

### Brain not indexing documents

```bash
# Check Elasticsearch connectivity
curl -u elastic:$ELASTIC_PASSWORD http://elasticsearch:9200/_cluster/health

# Check Neo4j connectivity
curl -u neo4j:$NEO4J_PASSWORD http://neo4j:7474/db/neo4j/

# Check brain logs for connection errors
docker logs intel_brain | grep -i "error\|connection\|elasticsearch"
```

### CAPTCHA solver not working

```bash
# Verify 2Captcha API key
curl https://2captcha.com/api/user?key=$CAPTCHA_2_KEY&action=userinfo

# Check Tesseract installed in collector-python image
docker exec intel_collector_py tesseract --version

# Manual test
docker exec intel_collector_py python -c "
from src.captcha_solver import CaptchaSolver
solver = CaptchaSolver('2captcha_key')
print('Ready')
"
```

## Next Steps

1. **Scale Out**: Run multiple collector-python instances with shared Redis dedup
2. **Multilingual NLP**: Integrate spaCy multilingual models (mBERT)
3. **Graph Analysis**: Query Neo4j for entity relationships and threat patterns
4. **Custom Crawl**: Update START_URL and ALLOWED_DOMAINS for your crawl targets
5. **Alert Integration**: Connect Prometheus alerts to incident response tools

## Architecture Documentation

See [PRODUCTION_ARCHITECTURE.md](./docs/PRODUCTION_ARCHITECTURE.md) for detailed system design, Phase 1-4 capabilities, and advanced configurations.

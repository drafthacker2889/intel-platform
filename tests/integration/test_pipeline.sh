#!/usr/bin/env bash
# End-to-end pipeline integration test.
#
# Starts a minimal stack (Redis + sanitizer + brain + Elasticsearch), pushes a
# synthetic raw_html payload, and verifies the document appears in Elasticsearch.
#
# Usage:
#   REDIS_PASSWORD=testpass bash tests/integration/test_pipeline.sh
#
# Requires: docker compose, redis-cli, curl, jq

set -euo pipefail

REDIS_PASSWORD="${REDIS_PASSWORD:-testpass}"
COMPOSE_FILE="docker-compose.yml"
ES_URL="http://localhost:9200"
ELASTIC_INDEX="${ELASTIC_INDEX:-intel-data-v3}"
RAW_QUEUE="${RAW_QUEUE_NAME:-raw_html}"
TIMEOUT=120   # seconds to wait for a document to appear in ES

export REDIS_PASSWORD

cleanup() {
    echo "[integration] Tearing down test stack…"
    docker compose -f "$COMPOSE_FILE" down --volumes --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

# ── 1. Start minimal services ─────────────────────────────────────────────────
echo "[integration] Starting redis, elasticsearch, sanitizer-rust, brain-python…"
docker compose -f "$COMPOSE_FILE" up -d \
    redis elasticsearch sanitizer-rust brain-python

# ── 2. Wait for Elasticsearch to be healthy ───────────────────────────────────
echo "[integration] Waiting for Elasticsearch…"
deadline=$(( $(date +%s) + TIMEOUT ))
until curl -sf "$ES_URL/_cluster/health" | grep -qv '"status":"red"'; do
    if [[ $(date +%s) -gt $deadline ]]; then
        echo "[integration] ERROR: Elasticsearch did not become healthy in ${TIMEOUT}s"
        exit 1
    fi
    sleep 3
done
echo "[integration] Elasticsearch is healthy."

# ── 3. Wait for brain-python health endpoint ──────────────────────────────────
echo "[integration] Waiting for brain-python health endpoint…"
deadline=$(( $(date +%s) + TIMEOUT ))
until curl -sf http://localhost:8082/health | grep -q '"status":"ready"'; do
    if [[ $(date +%s) -gt $deadline ]]; then
        echo "[integration] ERROR: brain-python did not become ready in ${TIMEOUT}s"
        exit 1
    fi
    sleep 3
done
echo "[integration] brain-python is ready."

# ── 4. Push a synthetic sanitized payload via the raw_html queue ──────────────
# We push directly into the sanitized_text queue so we bypass the HTML cleaner
# and test the brain<->ES path in isolation.
SANITIZED_QUEUE="${SANITIZED_QUEUE_NAME:-sanitized_text}"
TEST_PAYLOAD=$(cat <<'JSON'
{"text":"admin leaked the secret password for db_pass","source_url":"http://test.example/integration","traceparent":"00-aabbccddeeff00112233445566778899-0011223344556677-01","collected_at":"2026-01-01T00:00:00Z"}
JSON
)

echo "[integration] Pushing test payload to '$SANITIZED_QUEUE'…"
docker compose -f "$COMPOSE_FILE" exec -T redis \
    redis-cli -a "$REDIS_PASSWORD" LPUSH "$SANITIZED_QUEUE" "$TEST_PAYLOAD"

# ── 5. Wait for the document to appear in Elasticsearch ───────────────────────
echo "[integration] Waiting for document in Elasticsearch index '$ELASTIC_INDEX'…"
deadline=$(( $(date +%s) + TIMEOUT ))
FOUND=false
while [[ $(date +%s) -le $deadline ]]; do
    count=$(curl -sf "$ES_URL/$ELASTIC_INDEX/_count" | jq -r '.count // 0' 2>/dev/null || echo 0)
    if [[ "$count" -gt 0 ]]; then
        FOUND=true
        break
    fi
    sleep 3
done

if [[ "$FOUND" != "true" ]]; then
    echo "[integration] FAIL: No documents appeared in '$ELASTIC_INDEX' within ${TIMEOUT}s."
    exit 1
fi

# ── 6. Verify the document has expected fields ────────────────────────────────
DOC=$(curl -sf "$ES_URL/$ELASTIC_INDEX/_search?size=1" | jq -r '.hits.hits[0]._source')
echo "[integration] Document: $DOC"

for field in risk_label risk_score entities source_url collected_at; do
    if ! echo "$DOC" | jq -e ".$field" > /dev/null 2>&1; then
        echo "[integration] FAIL: missing field '$field' in indexed document."
        exit 1
    fi
done

RISK_LABEL=$(echo "$DOC" | jq -r '.risk_label')
echo "[integration] risk_label=$RISK_LABEL"
if [[ "$RISK_LABEL" != "CRITICAL" && "$RISK_LABEL" != "HIGH" ]]; then
    echo "[integration] FAIL: expected CRITICAL or HIGH risk_label for the test payload, got '$RISK_LABEL'."
    exit 1
fi

echo "[integration] PASS: document indexed with all required fields and correct risk label."

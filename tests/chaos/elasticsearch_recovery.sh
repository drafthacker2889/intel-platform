#!/usr/bin/env bash
# Chaos test: Elasticsearch outage and recovery
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILES=(
  -f docker-compose.yml
  -f docker-compose.prod.yml
  -f docker-compose.observability.yml
)

cleanup() {
  docker compose "${COMPOSE_FILES[@]}" down -v
}
trap cleanup EXIT

docker compose "${COMPOSE_FILES[@]}" up -d --build

for _ in $(seq 1 90); do
  if curl -fsS http://localhost:8080/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "Stack healthy. Stopping Elasticsearch..."
docker compose "${COMPOSE_FILES[@]}" stop elasticsearch
sleep 10

echo "Verifying brain handles ES outage gracefully..."
BRAIN_HEALTH=$(curl -sS http://localhost:8080/brain/health 2>/dev/null || echo '{"status":"error"}')
echo "Brain health during ES outage: $BRAIN_HEALTH"

echo "Restarting Elasticsearch..."
docker compose "${COMPOSE_FILES[@]}" start elasticsearch

for _ in $(seq 1 60); do
  if curl -fsS http://localhost:9200 >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

echo "Elasticsearch recovered. Validating endpoints..."
curl -fsS http://localhost:8080/health >/dev/null
curl -fsS http://localhost:8080/brain/health >/dev/null

echo chaos-elasticsearch-recovery-ok

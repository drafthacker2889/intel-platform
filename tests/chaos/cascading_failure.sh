#!/usr/bin/env bash
# Chaos test: Multi-service cascading failure (Redis + ES down simultaneously)
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

echo "Stack healthy. Stopping Redis AND Elasticsearch simultaneously..."
docker compose "${COMPOSE_FILES[@]}" stop redis elasticsearch
sleep 10

echo "Gateway should still answer /health..."
curl -fsS http://localhost:8080/health >/dev/null

echo "Restarting Redis first..."
docker compose "${COMPOSE_FILES[@]}" start redis
for _ in $(seq 1 30); do
  if docker exec intel_queue redis-cli ping 2>/dev/null | grep -q PONG; then
    break
  fi
  sleep 2
done

echo "Redis recovered. Restarting Elasticsearch..."
docker compose "${COMPOSE_FILES[@]}" start elasticsearch
for _ in $(seq 1 60); do
  if curl -fsS http://localhost:9200 >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

echo "Both services recovered. Validating full stack..."
curl -fsS http://localhost:8080/health >/dev/null
curl -fsS http://localhost:8080/brain/health >/dev/null

echo chaos-cascading-failure-ok

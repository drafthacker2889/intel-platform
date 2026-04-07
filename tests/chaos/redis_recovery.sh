#!/usr/bin/env bash
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

for _ in $(seq 1 60); do
  if curl -fsS http://localhost:8080/health >/dev/null; then
    break
  fi
  sleep 2
done

docker compose "${COMPOSE_FILES[@]}" stop redis
sleep 5
docker compose "${COMPOSE_FILES[@]}" start redis

for _ in $(seq 1 30); do
  if docker exec intel_queue redis-cli ping | grep -q PONG; then
    break
  fi
  sleep 2
done

curl -fsS http://localhost:8080/health >/dev/null
curl -fsS http://localhost:8080/brain/health >/dev/null

echo chaos-redis-recovery-ok

#!/bin/bash
set -euo pipefail

echo "Setting up Intel Platform environment..."

mkdir -p es_data neo4j_data redis_data

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
  else
    {
      echo "ELASTIC_PASSWORD=changeme-dev"
      echo "NEO4J_PASSWORD=changeme-dev"
      echo "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    } > .env
    echo "Created .env with fallback defaults"
  fi
else
  echo ".env already exists"
fi

echo "Setup complete. Run 'docker compose up --build' to start."

#!/bin/bash
echo "?? Setting up Intel Platform Environment..."

# Create necessary data folders so Docker doesn't complain
mkdir -p es_data neo4j_data redis_data

# Create a default .env file if it doesn't exist
if [ ! -f .env ]; then
  echo "ELASTIC_PASSWORD=changeme123" > .env
  echo "NEO4J_PASSWORD=changeme123" >> .env
  echo "?  .env file created."
else
  echo "??  .env file already exists."
fi

echo "?? Setup complete. Run 'docker-compose up --build' to start."

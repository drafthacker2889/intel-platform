#!/bin/bash
echo "??  WARNING: NUKING ALL DATA (Elastic, Redis, Neo4j)..."
docker-compose down -v
rm -rf es_data neo4j_data redis_data
echo "?  Clean slate established."

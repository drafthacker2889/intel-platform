"""Automated Elasticsearch schema backfill migration.

Reindexes documents from old schema-versioned indices into the current
schema version index, applying field transformations as needed.

Usage:
    python scripts/es_migrate.py --source-version v1 --target-version v2
    python scripts/es_migrate.py --auto   # migrates all old versions to current
"""

import argparse
import json
import os
import sys
import time

from elasticsearch import Elasticsearch, helpers

ES_HOST = os.getenv("ELASTIC_HOST", "http://localhost:9200")
ALIAS = os.getenv("ELASTIC_INDEX", "intel-data-v3")
CURRENT_SCHEMA = os.getenv("SCHEMA_VERSION", "v1")
BATCH_SIZE = 500


def connect():
    return Elasticsearch(ES_HOST, request_timeout=120)


def concrete_name(alias, version):
    return f"{alias}-{version}"


def discover_old_indices(es, alias, current_version):
    """Find all indices matching the alias pattern that aren't the current version."""
    pattern = f"{alias}-*"
    current = concrete_name(alias, current_version)
    indices = es.indices.get(index=pattern, ignore_unavailable=True)
    return [name for name in indices if name != current]


def get_index_doc_count(es, index):
    stats = es.count(index=index)
    return stats["count"]


def build_transform_script(source_version, target_version):
    """Painless script to stamp new schema_version on reindexed docs."""
    return {
        "source": f"ctx._source.schema_version = '{target_version}';"
    }


def reindex(es, source_index, target_index, target_version):
    """Reindex from source to target with version stamp transform."""
    print(f"  Reindexing {source_index} -> {target_index}")

    source_count = get_index_doc_count(es, source_index)
    print(f"  Source documents: {source_count}")

    if source_count == 0:
        print("  No documents to migrate, skipping.")
        return 0

    body = {
        "source": {"index": source_index, "size": BATCH_SIZE},
        "dest": {"index": target_index},
        "script": build_transform_script(
            source_index.split("-")[-1], target_version
        ),
        "conflicts": "proceed",
    }

    result = es.reindex(body=body, wait_for_completion=True, request_timeout=600)

    created = result.get("created", 0)
    updated = result.get("updated", 0)
    failures = result.get("failures", [])

    print(f"  Created: {created}, Updated: {updated}, Failures: {len(failures)}")

    if failures:
        for f in failures[:5]:
            print(f"    Failure: {json.dumps(f)}")

    return created + updated


def ensure_target_exists(es, alias, target_version, model_version):
    """Create the target index if needed (mirrors brain-python ensure_index logic)."""
    target = concrete_name(alias, target_version)
    if es.indices.exists(index=target):
        return target

    mapping = {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "content": {"type": "text"},
                "entities": {
                    "type": "nested",
                    "properties": {
                        "text": {"type": "keyword"},
                        "type": {"type": "keyword"},
                    },
                },
                "entity_count": {"type": "integer"},
                "risk_score": {"type": "integer"},
                "risk_label": {"type": "keyword"},
                "traceparent": {"type": "keyword"},
                "source_url": {"type": "keyword"},
                "schema_version": {"type": "keyword"},
                "model_version": {"type": "keyword"},
                "timestamp": {"type": "date"},
            },
            "_meta": {
                "schema_version": target_version,
                "model_version": model_version,
            },
        },
    }
    es.indices.create(index=target, body=mapping)
    print(f"  Created target index: {target}")
    return target


def update_alias(es, alias, target_index):
    """Point alias to target index, remove from all others."""
    try:
        current = es.indices.get_alias(name=alias)
        actions = []
        for idx in current:
            if idx != target_index:
                actions.append({"remove": {"index": idx, "alias": alias}})
        actions.append({"add": {"index": target_index, "alias": alias}})
        es.indices.update_aliases(body={"actions": actions})
    except Exception:
        es.indices.put_alias(index=target_index, name=alias)
    print(f"  Alias '{alias}' now points to {target_index}")


def migrate_single(es, source_version, target_version, model_version):
    source_index = concrete_name(ALIAS, source_version)
    if not es.indices.exists(index=source_index):
        print(f"Source index {source_index} does not exist.")
        return False

    target_index = ensure_target_exists(es, ALIAS, target_version, model_version)
    migrated = reindex(es, source_index, target_index, target_version)
    update_alias(es, ALIAS, target_index)
    print(f"  Migration complete: {migrated} documents from {source_version} -> {target_version}")
    return True


def auto_migrate(es, model_version):
    old_indices = discover_old_indices(es, ALIAS, CURRENT_SCHEMA)
    if not old_indices:
        print("No old indices found. Nothing to migrate.")
        return True

    target_index = ensure_target_exists(es, ALIAS, CURRENT_SCHEMA, model_version)
    total = 0
    for source_index in old_indices:
        migrated = reindex(es, source_index, target_index, CURRENT_SCHEMA)
        total += migrated

    update_alias(es, ALIAS, target_index)
    print(f"Auto-migration complete: {total} documents from {len(old_indices)} old index(es)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Elasticsearch schema migration")
    parser.add_argument("--source-version", help="Source schema version (e.g., v1)")
    parser.add_argument("--target-version", help="Target schema version (e.g., v2)")
    parser.add_argument("--model-version", default=os.getenv("MODEL_VERSION", "risk-rules-v2"))
    parser.add_argument("--auto", action="store_true", help="Auto-migrate all old versions to current")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without executing")
    args = parser.parse_args()

    es = connect()

    if args.dry_run:
        old = discover_old_indices(es, ALIAS, CURRENT_SCHEMA)
        for idx in old:
            count = get_index_doc_count(es, idx)
            print(f"  {idx}: {count} documents")
        if not old:
            print("No old indices found.")
        return

    if args.auto:
        success = auto_migrate(es, args.model_version)
    elif args.source_version and args.target_version:
        success = migrate_single(es, args.source_version, args.target_version, args.model_version)
    else:
        parser.print_help()
        return

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

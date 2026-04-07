# Model Governance

## Current Baseline

The intelligence scoring model is currently a versioned rule engine, not a learned classifier.

## Controls in Place

1. `MODEL_VERSION` is attached to every indexed document.
2. `SCHEMA_VERSION` is attached to every indexed document and Elasticsearch mapping metadata.
3. `services/brain-python/eval_model.py` runs a regression evaluation pack.
4. CI fails if evaluation accuracy drops below the configured threshold.

## Next Steps

1. Add larger labeled evaluation datasets.
2. Track precision, recall, and false-positive rate by label.
3. Introduce feature-flagged experimental models.
4. Add human review workflow for promoted model versions.

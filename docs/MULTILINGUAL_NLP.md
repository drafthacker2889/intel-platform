# Multilingual NLP Integration Guide

## Overview

The brain-python service now supports automatic language detection and entity extraction in **4 languages**:

- **English** (en) — Default, covered by original model
- **Russian** (ru) — Critical for dark web coverage
- **Chinese** (zh) — Mandarin/Simplified, for Asia-Pacific threats
- **German** (de) — Important for European threat intelligence

Language detection is automatic using `langdetect` library. Entities are extracted using language-specific spaCy models.

## Features

### 1. Automatic Language Detection

```python
from src.multilingual_nlp import MultilingualNLPManager

nlp = MultilingualNLPManager(logger)
lang_code, confidence = nlp.detect_language("Лазарус украл базу данных")
# Returns: ("ru", 0.95)

info = nlp.get_language_info(text)
# {
#   "language_code": "ru",
#   "language_name": "Russian",
#   "detection_confidence": 0.95,
#   "supported": True
# }
```

### 2. Multilingual Entity Extraction

```python
entities = nlp.extract_entities("LockBit leaked database of Fortune 500 company")
# Returns: [
#   {"text": "LockBit", "type": "ORG", "language": "en", ...},
#   {"text": "Fortune 500", "type": "ORG", "language": "en", ...}
# ]
```

Entity types are normalized across all languages:
- `PERSON` — Individual names
- `ORG` — Organizations, threat actors
- `LOCATION` — Countries, cities (mapped from GPE/LOC)
- `PRODUCT` — Software, technology (mapped from model-specific labels)
- `EMAIL` — Email addresses (when detected)
- `URL` — URLs (when detected)

### 3. Multilingual Synthetic Training Data

Generate realistic threat intelligence in all 4 languages:

```bash
# Generate 30,000 multilingual samples (7,500 per language)
cd services/brain-python
python generate_multilingual_data.py

# Output: evals/multilingual_eval_cases.json
# Format: [{"text": "...", "language": "ru", "expected_label": "CRITICAL", ...}, ...]
```

Distribution per language:
- 10% CRITICAL — Data breaches, credential leaks, active compromises
- 30% HIGH — Exploits, zero-days, malware analysis
- 40% MEDIUM — Security research, incident response
- 20% LOW — General news, documentation

**Threat Actors Included (localized names):**
- LockBit, Royal, BlackCat, Alphv, Lazarus Group, APT28
- Russian variants: "Лазарус", "Fancy Bear" (тактические группы)
- Chinese: "黑猫" (Black Cat alternative transliteration)

### 4. Elasticsearch Document Enhancement

All indexed documents now include language metadata:

```json
{
  "content": "...",
  "language_code": "ru",
  "language_name": "Russian",
  "language_confidence": 0.95,
  "entities": [
    {"text": "Лазарус", "type": "ORG", "language": "ru"}
  ],
  "risk_label": "CRITICAL"
}
```

### 5. Language-Specific Pipelines

Future enhancement: Process per-language documents through language-specific risk models:

```python
# Pseudocode (not yet implemented)
if doc["language_code"] == "ru":
    risk_model = models["risk_ml_v1_ru"]  # Russian-trained model
elif doc["language_code"] == "zh":
    risk_model = models["risk_ml_v1_zh"]  # Chinese-trained model
else:
    risk_model = models["risk_ml_v1_en"]  # Default English model

risk_score = risk_model.predict(features)
```

## Setup

### Automated Model Download

Models are downloaded during Docker build (in Dockerfile):

```dockerfile
RUN python -m spacy download en_core_web_sm && \
    python -m spacy download ru_core_news_sm && \
    python -m spacy download zh_core_web_sm && \
    python -m spacy download de_core_news_sm
```

### Manual Download (Development)

**Linux/macOS:**
```bash
cd services/brain-python
bash download_models.sh
```

**Windows PowerShell:**
```powershell
cd services\brain-python
.\download_models.ps1
```

**Individual models:**
```bash
python -m spacy download en_core_web_sm      # English
python -m spacy download ru_core_news_sm     # Russian
python -m spacy download zh_core_web_sm      # Chinese
python -m spacy download de_core_news_sm     # German
```

### Configuration

Environment variables (optional):

```bash
# Prefer a language model for fallback (default: en)
MULTILINGUAL_PREFER_LANG=en

# Disable multilingual NLP (use English only)
MULTILINGUAL_DISABLED=false
```

## Dependencies

New requirements added to `requirements.txt`:

```
langdetect==1.0.9      # Language detection
spacy==3.7.2           # Already present, now with multilingual models
```

No additional ML frameworks required (mBERT support can be added in future with transformers library).

## Model Information

### spaCy Models

| Language | Model | Size | Entity Types |
|----------|-------|------|--------------|
| English | en_core_web_sm | 37.3M | PERSON, ORG, GPE, PRODUCT, etc. |
| Russian | ru_core_news_sm | 44.4M | PERSON, ORG, GPE, LOCATION |
| Chinese | zh_core_web_sm | 56.8M | PERSON, ORG, GPE, PRODUCT |
| German | de_core_news_sm | 51.9M | PERSON, ORG, GPE, PRODUCT |

**Total model size: ~190MB** (significant but acceptable for production containers)

### langdetect

- Uses Naive Bayes trained on Wikipedia articles
- Accuracy: ~94-97% for text segments > 50 characters
- Supports 55+ languages (we use 4)
- Extremely fast (~1ms per detection)

## Integration with Training

### Training with Multilingual Data

```bash
cd services/brain-python

# 1. Generate 30K multilingual samples
python generate_multilingual_data.py

# 2. Train model (will auto-use both English + multilingual data if both exist)
python train_risk_model.py

# Output: models/risk_model.joblib (now trained on English + Russian + Chinese + German)
```

### Model Evaluation

Query Elasticsearch for language distribution of indexed documents:

```json
POST /intel-data-v3/_search
{
  "aggs": {
    "language_distribution": {
      "terms": { "field": "language_code" }
    }
  }
}
```

Response:
```json
{
  "aggregations": {
    "language_distribution": {
      "buckets": [
        {"key": "en", "doc_count": 850},
        {"key": "ru", "doc_count": 340},
        {"key": "zh", "doc_count": 210},
        {"key": "de", "doc_count": 145}
      ]
    }
  }
}
```

## Usage Examples

### Example 1: Process Russian Threat Intelligence

```python
import redis
from src.multilingual_nlp import MultilingualNLPManager

nlp = MultilingualNLPManager(logger)

russian_text = "Лазарус украл базу данных Bank of Moscow с 50000 кредитных карт"

# Detect language
lang, conf = nlp.detect_language(russian_text)
print(f"Detected: {lang} ({conf:.2%})")  # Output: ru (95%)

# Extract entities
entities = nlp.extract_entities(russian_text)
print(f"Found entities: {len(entities)}")
for ent in entities:
    print(f"  - {ent['text']} ({ent['type']})")
    # Output:
    # - Лазарус (ORG)
    # - Bank of Moscow (ORG)
```

### Example 2: Index Document with Language Metadata

```python
# In brain-python/src/main.py (automated)
lang_info = get_language_info(clean_text)

doc = {
    "content": clean_text,
    "language_code": lang_info["language_code"],    # "ru"
    "language_name": lang_info["language_name"],    # "Russian"
    "language_confidence": lang_info["detection_confidence"],  # 0.95
    "entities": entities,
    "risk_label": risk_label,
}

es.index(index="intel-data-v3", document=doc)
```

### Example 3: Query by Language

```bash
# Get all CRITICAL documents in Russian
curl -X GET "localhost:9200/intel-data-v3/_search" -H "Content-Type: application/json" -d '
{
  "query": {
    "bool": {
      "must": [
        {"term": {"language_code": "ru"}},
        {"term": {"risk_label": "CRITICAL"}}
      ]
    }
  }
}'
```

## Limitations & Future Enhancements

### Current Limitations

1. **Small models used** — spaCy small models (en_core_web_sm) have limited accuracy. For production, consider medium models (en_core_web_md).
2. **No cross-language transfer** — Each language model is independent; no multilingual BERT embeddings.
3. **Entity type variance** — Different languages may label same entity differently (GPE vs LOC).

### Future Enhancements (Phase 4+)

1. **Multilingual BERT (mBERT)**
   - Better entity extraction accuracy across languages
   - Semantic similarity search in all 4 languages
   - Requires `transformers` library (~2GB model weights)

2. **Language-Specific Risk Models**
   - Train separate RandomForest models per language
   - Each with language-specific keywords and threat patterns
   - Route documents through appropriate model

3. **Cross-Language Entity Linking**
   - "Лазарус" → "Lazarus Group" → entity deduplication
   - Multilingual Neo4j relationships (mentions across languages)

4. **Real-Time Language Switching**
   - Add language selector to dashboard UI
   - Filter results by selected language
   - Show language confidence scores

## Troubleshooting

### Models not downloading in Docker

```bash
# Check if spacy is installed
docker exec intel_brain python -c "import spacy; print(spacy.__version__)"

# Manually download missing models
docker exec intel_brain python -m spacy download ru_core_news_sm
```

### Language detection accuracy low

```python
# For very short text, accuracy degrades; consider:
if len(text.strip()) < 20:
    return "en", 0.3  # Low confidence, fallback to English

# For mixed-language text, first 500 chars are used
# Can adjust detection window: nlp.detect_language(text, window_size=1000)
```

### Entity extraction incomplete

```python
# Check if model is loaded
from src.multilingual_nlp import MultilingualNLPManager
nlp = MultilingualNLPManager(logger)
nlp._load_model("ru")  # Pre-load Russian model

# If specific entities missing, may need larger spaCy models:
python -m spacy download ru_core_news_md  # 50M instead of 44M
```

## References

- [spaCy Multilingual Models](https://spacy.io/models)
- [langdetect GitHub](https://github.com/Mimino666/langdetect)
- [Language Detection Evaluation](https://github.com/Mimino666/langdetect/wiki/Accuracy)

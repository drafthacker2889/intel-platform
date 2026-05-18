# Model Training Guide

Complete guide to generating synthetic data, training ML models, and deploying to production.

## Overview

The system uses **synthetic threat intelligence data** to train a production-grade RandomForest risk classifier. Three levels of training are available:

1. **Basic** — English synthetic data only (10K samples)
2. **Advanced** — English + Multilingual synthetic data (40K samples) + augmentation
3. **Custom** — Using your own labeled datasets

## Quick Start (Recommended Path)

```bash
cd services/brain-python

# Step 1: Generate English synthetic data (10K samples)
python generate_synthetic_data.py
# Output: evals/risk_eval_cases.json

# Step 2: Generate multilingual data (30K samples, 4 languages)
python generate_multilingual_data.py
# Output: evals/multilingual_eval_cases.json

# Step 3: Train advanced model (combines both datasets + augmentation)
python train_advanced_model.py
# Output: models/risk_model_advanced.joblib, models/risk_model.joblib

# Step 4: Optional — Evaluate model on test cases
python eval_model.py
```

**Total time:** ~5 minutes on modern hardware

## Training Approaches

### 1. Basic Training (English Only)

**For rapid prototyping, CI/CD pipelines, or memory-constrained environments.**

```bash
python generate_synthetic_data.py
python train_risk_model.py
```

**Output:**
- `models/risk_model.joblib` — Trained on 10K English samples
- Cross-validation F1 score: 0.85-0.90
- Classes: CRITICAL (10%), HIGH (30%), MEDIUM (40%), LOW (20%)

### 2. Advanced Training (Recommended for Production)

**Multilingual support, data augmentation, advanced metrics.**

```bash
# Generate both datasets
python generate_synthetic_data.py          # 10K English
python generate_multilingual_data.py        # 30K Multilingual

# Train advanced model
python train_advanced_model.py
```

**Features:**
- Combined dataset: 40K samples (7.5K per language)
- Data augmentation: 5-10% additional synthetic variations
- Class balancing: Handles imbalanced label distribution
- Stratified K-fold cross-validation (k=3)
- ROC-AUC scoring for multi-class classification
- Feature importance analysis
- Both train and test accuracy reported

**Output:**
- `models/risk_model_advanced.joblib` — Advanced model (recommended)
- `models/risk_model.joblib` — Compatibility symlink
- `models/scaler.pkl` — Feature scaler (required for inference)

**Performance (typical):**
- Test accuracy: 88-92%
- Weighted F1 score: 0.87-0.91
- Per-class precision/recall/F1 breakdown
- ROC-AUC: 0.92-0.95

### 3. Custom Training

**For specific threat domains or proprietary datasets.**

Create JSON file with structure:

```json
[
  {
    "text": "LockBit leaked database with 50000 records",
    "expected_label": "CRITICAL",
    "language": "en",
    "entities": [
      {"text": "LockBit", "type": "ORG"},
      {"text": "50000", "type": "NUMBER"}
    ]
  },
  ...
]
```

Then update `train_advanced_model.py` to load your dataset:

```python
# In SyntheticDataLoader.load()
custom_path = self.base_path / "evals" / "custom_dataset.json"
with open(custom_path, "r") as f:
    custom_samples = json.load(f)
```

## Data Composition

### English Dataset (10K samples)

Generated via `generate_synthetic_data.py`

**Threat Actors:**
- LockBit, Royal, BlackCat, Alphv, Cl0p, Evil Corp
- Lazarus Group, APT28, Carbanak, FIN7

**Threat Categories:**
- CRITICAL (10%): Database dumps, credential leaks, admin passwords
- HIGH (30%): Exploits, zero-days, malware analysis, RATs
- MEDIUM (40%): Security research, incident response, threat hunts
- LOW (20%): General news, documentation, events

### Multilingual Dataset (30K samples)

Generated via `generate_multilingual_data.py` (7,500 per language)

**Languages:**
- **English (en):** Primary threat intelligence language
- **Russian (ru):** Dark web forums, threat actors (LockBit, Lazarus variants)
- **Chinese (zh):** APT-C groups, state-sponsored activity
- **German (de):** European organizations, financial institutions

**Localized Content:**
- Threat actors with native names (e.g., "Lazarus" → "Лазарус")
- Region-specific organizations (banks, companies by country)
- Technology names translated for naturalness

## Training Workflow Details

### Step 1: Data Generation

```bash
# English synthetic data
python generate_synthetic_data.py

# Console output:
# Generating 1000 CRITICAL samples...
# Generating 3000 HIGH samples...
# Generating 4000 MEDIUM samples...
# Generating 2000 LOW samples...
# Generated 10000 samples to evals/risk_eval_cases.json
#
# Label distribution:
#   CRITICAL: 1000 (10.0%)
#   HIGH: 3000 (30.0%)
#   MEDIUM: 4000 (40.0%)
#   LOW: 2000 (20.0%)
```

**Output size:** ~2.5MB JSON

```bash
# Multilingual data
python generate_multilingual_data.py

# Console output:
# Generating 7500 samples in EN...
# Generating 7500 samples in RU...
# Generating 7500 samples in ZH...
# Generating 7500 samples in DE...
# Generated 30000 multilingual samples to evals/multilingual_eval_cases.json
#
# Language distribution:
#   EN: 7500 (25.0%)
#   RU: 7500 (25.0%)
#   ZH: 7500 (25.0%)
#   DE: 7500 (25.0%)
```

**Output size:** ~8MB JSON

### Step 2: Data Augmentation

Applied during advanced training:

- **CRITICAL samples:** 2-3 variations (prefix: "URGENT:", "[BREACH]")
- **HIGH samples:** 1-2 variations (prefix: "[ALERT]", "Risk:")
- **MEDIUM/LOW:** No augmentation (reduce noise)

Result: 40K → ~43K samples (7.5% increase)

### Step 3: Feature Extraction

For each text, extract 5 features via `featurize()`:

1. **keyword_count** — Number of RISK_KEYWORDS found
2. **entity_count** — Number of named entities extracted
3. **text_length** — Length of text in characters
4. **url_count** — Number of URLs in text
5. **@_count** — Number of @ symbols (email/handle indicators)

### Step 4: Model Training

**RandomForestClassifier parameters:**

```python
n_estimators=150          # Number of decision trees
max_depth=8               # Prevent overfitting
min_samples_split=5       # Min samples to split node
min_samples_leaf=2        # Min samples in leaf
class_weight="balanced"   # Handle imbalanced classes
random_state=42           # Reproducibility
```

**Train/test split:**
- 80% training (32K samples)
- 20% testing (8K samples)
- Stratification ensures class balance in both sets

### Step 5: Cross-Validation

**Stratified K-Fold (k=3):**

```
Fold 1: Train on 66% (21.3K), validate on 33% (10.7K)
Fold 2: Train on 66% (21.3K), validate on 33% (10.7K)
Fold 3: Train on 66% (21.3K), validate on 33% (10.7K)
Mean F1-weighted: 0.88 ± 0.02
```

### Step 6: Evaluation

**Classification metrics on test set:**

```
               precision    recall  f1-score   support

      CRITICAL       0.92      0.89      0.90       800
          HIGH       0.87      0.88      0.87      2400
        MEDIUM       0.85      0.87      0.86      3200
           LOW       0.88      0.86      0.87      1600

    accuracy                           0.87      8000
   macro avg       0.88      0.87      0.88      8000
weighted avg       0.87      0.87      0.87      8000
```

**Feature importance:**

```
entity_count     0.421  (44%)  — Most important
keyword_count    0.283  (28%)
text_length      0.189  (19%)
@_count          0.073  (7%)
url_count        0.034  (3%)
```

## Performance Tuning

### If accuracy is too low (<80%):

1. **Increase data diversity**
   - Add real labeled samples from your crawl
   - Expand threat actor/organization names
   - Add industry-specific keywords

2. **Adjust feature engineering**
   - Add more domain-specific features
   - Increase RISK_KEYWORDS list in featurize.py
   - Add language-specific keyword sets

3. **Tune hyperparameters**
   - `n_estimators`: Increase to 200-300 for more diversity
   - `max_depth`: Increase to 10-12 for more complexity
   - `class_weight`: Try `"balanced_subsample"`

### If model is slow in production:

1. **Reduce model complexity**
   - Decrease `n_estimators` (100 instead of 150)
   - Decrease `max_depth` (6 instead of 8)

2. **Use model compression**
   - Consider LightGBM or XGBoost (faster inference)
   - Serialize with ONNX for language-agnostic deployment

### If model overfits (high train, low test accuracy):

1. **Increase regularization**
   - Increase `min_samples_split` (10 instead of 5)
   - Increase `min_samples_leaf` (5 instead of 2)

2. **Reduce training data**
   - Use only most recent/relevant samples
   - Reduce augmentation intensity

## Deployment

### In Docker (production stack)

Models are mounted from host:

```yaml
brain-python:
  volumes:
    - ./services/brain-python/models:/app/models:ro
  environment:
    - RISK_MODEL_PATH=/app/models/risk_model.joblib
    - SCORING_STRATEGY=ml  # Use ML model instead of rules
```

### Loading in inference:

```python
import joblib

# Load model and scaler
model = joblib.load("models/risk_model.joblib")
scaler = joblib.load("models/scaler.pkl")

# Featurize text
features = featurize(text, [])
features_scaled = scaler.transform([features])

# Predict
prediction = model.predict(features_scaled)[0]  # 0-3 (LOW-CRITICAL)
probabilities = model.predict_proba(features_scaled)[0]  # Confidence per class
```

## Retraining Pipeline

Recommended retraining schedule:

**Weekly:**
- Collect new labeled documents from crawl
- Augment with synthetic variations
- Evaluate on holdout test set

**Monthly:**
- Retrain model on combined dataset (old + new)
- Compare test accuracy against previous model
- A/B test in canary deployment

**Quarterly:**
- Deep analysis of misclassifications
- Update threat actor/keyword lists
- Adjust label distribution if skewed

## Scripts Reference

| Script | Input | Output | Time |
|--------|-------|--------|------|
| `generate_synthetic_data.py` | — | `evals/risk_eval_cases.json` (10K) | 10s |
| `generate_multilingual_data.py` | — | `evals/multilingual_eval_cases.json` (30K) | 30s |
| `train_risk_model.py` | `risk_eval_cases.json` | `models/risk_model.joblib` | 2-3m |
| `train_advanced_model.py` | Both JSON files | `models/risk_model_advanced.joblib` + metrics | 5-8m |
| `eval_model.py` | `risk_model.joblib` | Test predictions + metrics | 1m |

## Troubleshooting

### "No module named featurize"

```bash
cd services/brain-python
# Ensure you're running from the right directory
python train_advanced_model.py
```

### "langdetect not installed"

```bash
pip install langdetect==1.0.9
```

### Model file is huge (>1GB)

- Using too many estimators — reduce `n_estimators` to 50-100
- Serialization issue — verify using `joblib.load()` and checking memory

### "RISK_KEYWORDS not defined"

Ensure `src/featurize.py` is imported correctly. Should have:

```python
RISK_KEYWORDS = [
    "database dump", "admin password", "leaked", ...
]
```

## Advanced Topics

### Multi-Language Risk Models

Train separate models per language:

```python
for lang in ["en", "ru", "zh", "de"]:
    lang_samples = [s for s in samples if s["language"] == lang]
    trainer.train(lang_samples, f"models/risk_model_{lang}.joblib")
```

Then in brain-python:

```python
lang_code = get_language_info(text)["language_code"]
model = joblib.load(f"models/risk_model_{lang_code}.joblib")
```

### Ensemble Models

Combine multiple models for better robustness:

```python
from sklearn.ensemble import VotingClassifier

model1 = RandomForestClassifier(n_estimators=100)
model2 = RandomForestClassifier(n_estimators=150, max_depth=10)
model3 = GradientBoostingClassifier()

ensemble = VotingClassifier(
    estimators=[("rf1", model1), ("rf2", model2), ("gb", model3)],
    voting="soft"
)
```

### Feature Selection

Identify most important features:

```python
from sklearn.feature_selection import SelectKBest, f_classif

selector = SelectKBest(f_classif, k=3)
X_selected = selector.fit_transform(X, y)
```

## References

- [scikit-learn RandomForest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html)
- [Cross-validation Guide](https://scikit-learn.org/stable/modules/cross_validation.html)
- [Feature Scaling](https://scikit-learn.org/stable/modules/preprocessing.html#standardization-centering-and-scaling)

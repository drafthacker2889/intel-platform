FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (cached layer — only invalidated when requirements change).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download multilingual spaCy models when available.
# Builds should still succeed in restricted/offline environments.
RUN python - <<'PY'
from spacy.cli import download

models = [
    "en_core_web_sm",
    "ru_core_news_sm",
    "zh_core_web_sm",
    "de_core_news_sm",
]

for model in models:
    try:
        download(model)
        print(f"Installed spaCy model: {model}")
    except Exception as exc:
        print(f"Skipping spaCy model {model}: {exc}")
PY

# Copy source and training artefacts.
COPY src/           ./src/
COPY evals/         ./evals/
COPY train_risk_model.py .
COPY eval_model.py .
COPY generate_synthetic_data.py .
COPY generate_multilingual_data.py .

# Model training is NOT done at build time to keep images deterministic and fast.
# The model is trained once offline and the resulting file is mounted at runtime via
# RISK_MODEL_PATH, or the service falls back to rule-based scoring when the path is
# absent (SCORING_STRATEGY=auto).
ENV RISK_MODEL_PATH=/app/models/risk_model.joblib
ENV SCORING_STRATEGY=auto

RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 8082
CMD ["python", "src/main.py"]

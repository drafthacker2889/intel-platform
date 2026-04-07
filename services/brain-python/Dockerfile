FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY evals/ ./evals/
COPY train_risk_model.py .
COPY eval_model.py .

RUN python train_risk_model.py

ENV RISK_MODEL_PATH=/app/models/risk_model.joblib
ENV SCORING_STRATEGY=auto

EXPOSE 8082
CMD ["python", "src/main.py"]

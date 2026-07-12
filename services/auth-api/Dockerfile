FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --upgrade "pip>=25.0" "setuptools>=78.1.1" "wheel>=0.46.2" "jaraco.context>=6.1.0"

COPY src/ ./src/
COPY users.json ./users.json

RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 8084
CMD ["python", "src/main.py"]

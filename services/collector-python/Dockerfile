FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/tmp/playwright

WORKDIR /app

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libsm6 libxext6 libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium

COPY src/ ./src/

RUN useradd -m -u 1000 crawler && \
    chown -R crawler:crawler /app /tmp/playwright
USER crawler

EXPOSE 8081

CMD ["python", "src/main.py"]

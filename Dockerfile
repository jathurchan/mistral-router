FROM python:3.11-slim

# Install curl, which is required for the healthcheck in docker-compose.yml
RUN apt-get update && apt-get install -y curl && \
    # Clean up apt cache
    rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_PORT=8000

WORKDIR /app

RUN addgroup --system appuser && adduser --system --ingroup appuser appuser

RUN pip install --upgrade pip wheel

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY core/ ./core/

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE ${APP_PORT}

CMD ["uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "${APP_PORT}"]
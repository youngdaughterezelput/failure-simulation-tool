FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/failure-simulator.db \
    TARGET_API_URL=http://upstream:9000

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY app ./app

RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 simulator \
    && mkdir -p /data \
    && chown simulator:simulator /data

USER simulator

EXPOSE 8080
VOLUME ["/data"]

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8080/health')"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

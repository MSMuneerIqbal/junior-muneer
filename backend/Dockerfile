# The backend (FastAPI). Built from the project folder: docker compose build
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data

WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The app reads agents, playbooks and news sources from the project folder (one level up).
COPY agents /app/agents
COPY playbooks /app/playbooks
COPY news /app/news
COPY backend /app/backend

# Keys come from backend/.env through docker-compose (env_file), never baked into the image.
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
# One process only (no --workers): WhatsApp order, sign-ins in progress and live calls are kept in memory.
CMD ["python", "-m", "uvicorn", "junior.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

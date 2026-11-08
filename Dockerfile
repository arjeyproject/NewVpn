# NewVpn — single application image (bot / subscription API / worker share it)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
        openssl curl ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY scripts ./scripts

RUN mkdir -p /etc/newvpn/xray /app/backups

# default command set per-service in docker-compose.yml
CMD ["python", "-m", "app.bot.main"]

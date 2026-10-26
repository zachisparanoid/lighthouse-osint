# syntax=docker/dockerfile:1
# Build context is the repo ROOT (see docker-compose.yml) so we can pull in the
# generated shared-types Python package alongside the API source.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System libraries:
#  - build-essential / libffi-dev: occasional source builds (cffi, etc.)
#  - libpango/cairo/gdk-pixbuf/shared-mime-info/fonts: WeasyPrint PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libcairo2 \
        shared-mime-info \
        fonts-dejavu-core \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 1) Install the generated shared contracts package (rarely changes).
COPY packages/shared-types/python /opt/shared-types
RUN pip install /opt/shared-types

# 2) Install Python deps as a cached layer (changes only when requirements change).
COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# 3) Copy the API source last (changes most often).
COPY apps/api/ /app/

# Reports output dir (also mounted as a volume in compose).
RUN mkdir -p /data/reports

EXPOSE 8000

# Default command is overridden per-service in docker-compose.yml
# (uvicorn for api, celery worker/beat, alembic for migrate).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

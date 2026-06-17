# syntax=docker/dockerfile:1

FROM python:3.13-slim AS base

# - PYTHONDONTWRITEBYTECODE: no .pyc files in the container
# - PYTHONUNBUFFERED: stream logs straight to stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Runtime system libraries:
#   libpq5                         -> psycopg2 (PostgreSQL)
#   libpango / cairo / gdk-pixbuf  -> WeasyPrint PDF rendering
#   libjpeg / zlib                 -> Pillow image handling
#   gettext                        -> Django i18n (compilemessages)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libcairo2 \
        libffi8 \
        libjpeg62-turbo \
        zlib1g \
        shared-mime-info \
        fonts-dejavu-core \
        gettext \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so the layer is cached across code changes.
# build-essential + libpq-dev are only needed to compile wheels, then removed.
COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && pip install -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Run as an unprivileged user. Create the writable dirs it needs and hand them over.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]

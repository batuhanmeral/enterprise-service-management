#!/bin/sh
set -e

# Wait for the database to accept connections before doing anything that needs it.
if [ -n "$DB_HOST" ]; then
    echo "Waiting for database at $DB_HOST:${DB_PORT:-5432}..."
    until python -c "import socket,os,sys; s=socket.socket(); s.settimeout(2); \
sys.exit(0) if not s.connect_ex((os.environ['DB_HOST'], int(os.environ.get('DB_PORT','5432')))) else sys.exit(1)" 2>/dev/null; do
        echo "  database unavailable, retrying in 2s..."
        sleep 2
    done
    echo "Database is up."
fi

# Apply migrations and gather static assets on every boot (both are idempotent).
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Compile translation catalogs if any exist.
if [ -d locale ]; then
    python manage.py compilemessages 2>/dev/null || true
fi

exec "$@"

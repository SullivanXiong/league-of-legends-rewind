#!/bin/sh
set -e

# Ensure database is ready for SQLite (no wait needed); for Postgres use wait-for.

python manage.py collectstatic --noinput >/dev/null 2>&1 || true
python manage.py makemigrations || true
python manage.py migrate --noinput

# Check if we're running as a Celery worker or beat scheduler
if [ "$1" = "celery" ]; then
    echo "Starting Celery worker..."
    exec celery -A config worker -l info --concurrency=1
elif [ "$1" = "celery-beat" ]; then
    echo "Starting Celery beat scheduler..."
    exec celery -A config beat -l info
else
    exec python manage.py runserver 0.0.0.0:8000
fi


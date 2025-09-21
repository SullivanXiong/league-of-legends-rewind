#!/bin/sh
set -e

# Ensure database is ready for SQLite (no wait needed); for Postgres use wait-for.

python manage.py collectstatic --noinput >/dev/null 2>&1 || true
python manage.py makemigrations || true
python manage.py migrate --noinput

exec python manage.py runserver 0.0.0.0:8000


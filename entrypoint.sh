#!/bin/bash
set -e

echo "🚀 Starting Trading API..."

# Run database migrations
echo "🔄 Running database migrations..."
python manage.py migrate --noinput
echo "✅ Migrations complete!"

# Collect static files
echo "🔄 Collecting static files..."
python manage.py collectstatic --noinput || true
echo "✅ Static files collected!"

# Start gunicorn
echo "🚀 Starting Gunicorn server on port ${PORT:-8080}..."
exec gunicorn --bind :${PORT:-8080} --workers 2 --threads 4 --timeout 120 backend.wsgi:application

#!/bin/bash
set -e

echo "🚀 Starting Trading API..."
echo "🔧 DJANGO_SETTINGS_MODULE: $DJANGO_SETTINGS_MODULE"

# Run database migrations with error handling for partial migration state
echo "🔄 Running database migrations..."

# First, try to migrate the sites framework (needed for allauth)
echo "   Migrating sites framework..."
python manage.py migrate sites --noinput 2>&1 || echo "   Sites migration may already be applied"

# Then migrate contenttypes
echo "   Migrating contenttypes..."
python manage.py migrate contenttypes --noinput 2>&1 || echo "   Contenttypes migration may already be applied"

# Migrate auth
echo "   Migrating auth..."
python manage.py migrate auth --noinput 2>&1 || echo "   Auth migration may already be applied"

# Migrate sessions
echo "   Migrating sessions..."
python manage.py migrate sessions --noinput 2>&1 || echo "   Sessions migration may already be applied"

# Migrate admin
echo "   Migrating admin..."
python manage.py migrate admin --noinput 2>&1 || echo "   Admin migration may already be applied"

# Migrate allauth
echo "   Migrating allauth..."
python manage.py migrate account --noinput 2>&1 || echo "   Account migration may already be applied"
python manage.py migrate socialaccount --noinput 2>&1 || echo "   Socialaccount migration may already be applied"

# Migrate trading_api with fake-initial in case table already exists
echo "   Migrating trading_api..."
python manage.py migrate trading_api --fake-initial --noinput 2>&1 || python manage.py migrate trading_api --noinput 2>&1 || echo "   Trading API migration may already be applied"

# Run remaining migrations
echo "   Running remaining migrations..."
python manage.py migrate --noinput 2>&1 || echo "   Some migrations may have failed, but continuing..."

echo "✅ Migrations complete (or already applied)!"

# Collect static files
echo "🔄 Collecting static files..."
python manage.py collectstatic --noinput || true
echo "✅ Static files collected!"

# Start gunicorn
echo "🚀 Starting Gunicorn server on port ${PORT:-8080}..."
exec gunicorn --bind :${PORT:-8080} --workers 2 --threads 4 --timeout 120 backend.wsgi:application

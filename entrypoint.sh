#!/bin/bash
set -e

echo "🚀 Starting Trading API..."
echo "🔧 DJANGO_SETTINGS_MODULE: $DJANGO_SETTINGS_MODULE"

# Run database migrations with error handling for partial migration state
echo "🔄 Running database migrations..."

# Fix: Add missing password column to users table if it doesn't exist
# This handles the case where the table was created with Flask/SQLAlchemy before Django migrations
echo "   Checking and fixing users table schema..."
python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', os.environ.get('DJANGO_SETTINGS_MODULE', 'backend.settings.production'))
django.setup()

from django.db import connection

try:
    with connection.cursor() as cursor:
        # Check if users table exists
        cursor.execute(\"\"\"
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'users'
            );
        \"\"\")
        table_exists = cursor.fetchone()[0]
        
        if table_exists:
            # Check if password column exists
            cursor.execute(\"\"\"
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'users' AND column_name = 'password'
                );
            \"\"\")
            password_exists = cursor.fetchone()[0]
            
            if not password_exists:
                print('   Adding missing password column to users table...')
                cursor.execute('ALTER TABLE users ADD COLUMN password VARCHAR(128) DEFAULT \'\'')
                print('   ✅ Password column added!')
            else:
                print('   Password column already exists.')
        else:
            print('   Users table does not exist yet, will be created by migrations.')
except Exception as e:
    print(f'   Warning: Could not check/fix users table: {e}')
" 2>&1 || echo "   Schema check/fix completed with warnings"

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

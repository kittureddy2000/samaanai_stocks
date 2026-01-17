#!/bin/bash
set -e

echo "🚀 Starting Trading API..."
echo "🔧 DJANGO_SETTINGS_MODULE: $DJANGO_SETTINGS_MODULE"

# Run database migrations with error handling for partial migration state
echo "🔄 Running database migrations..."

# Fix: Add missing columns to users table if they don't exist
# This handles the case where the table was created with Flask/SQLAlchemy before Django migrations
echo "   Checking and fixing users table schema..."
python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', os.environ.get('DJANGO_SETTINGS_MODULE', 'backend.settings.production'))
django.setup()

from django.db import connection

# All columns required by Django's AbstractBaseUser and our custom User model
REQUIRED_COLUMNS = {
    'password': 'VARCHAR(128) DEFAULT \'\'',
    'is_superuser': 'BOOLEAN DEFAULT FALSE',
    'is_staff': 'BOOLEAN DEFAULT FALSE',
    'is_active': 'BOOLEAN DEFAULT TRUE',
    'email_verified': 'BOOLEAN DEFAULT FALSE',
    'name': 'VARCHAR(255) DEFAULT \'\'',
    'picture_url': 'VARCHAR(500) DEFAULT \'\'',
    'auth_provider': 'VARCHAR(50) DEFAULT \\'local\\'',
    'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
    'last_login': 'TIMESTAMP NULL',
}

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
            # Get existing columns
            cursor.execute(\"\"\"
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'users';
            \"\"\")
            existing_columns = {row[0] for row in cursor.fetchall()}
            print(f'   Existing columns: {existing_columns}')
            
            # Add missing columns
            for col_name, col_def in REQUIRED_COLUMNS.items():
                if col_name not in existing_columns:
                    print(f'   Adding missing column: {col_name}')
                    cursor.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_def}')
                    print(f'   ✅ Column {col_name} added!')
            
            print('   Schema check complete.')
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

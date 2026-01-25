"""
Production settings for LLM Trading Agent project (Google Cloud Run).
"""

import os
from .base import *

DEBUG = False

# Secret key - required at runtime, but allow build-time with dummy value
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'build-time-dummy-key-replace-at-runtime')

# At runtime, we check if the real secret key is set
# This allows collectstatic to work during Docker build
def _check_secret_key():
    """Check that a real secret key is set (called at app startup)."""
    if SECRET_KEY == 'build-time-dummy-key-replace-at-runtime':
        import warnings
        warnings.warn("DJANGO_SECRET_KEY not set - using dummy key (not safe for production)")

# Allowed hosts from environment plus hardcoded Cloud Run domains
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS if host.strip()]

# Always include Cloud Run domains
CLOUD_RUN_HOSTS = [
    'trading-api-staging-hdp6ioqupa-uc.a.run.app',
    'trading-dashboard-staging-hdp6ioqupa-uc.a.run.app',
    'stg.trading.samaanai.com',
    'trading.samaanai.com',
    '.run.app',  # Wildcard for all Cloud Run
]
for host in CLOUD_RUN_HOSTS:
    if host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)

# Allow all hosts if none configured (fallback)
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ['*']


# Database - Google Cloud SQL (PostgreSQL)
# Supports both Unix socket (Cloud Run) and TCP (local) connections
INSTANCE_CONNECTION_NAME = os.environ.get('INSTANCE_CONNECTION_NAME', '')
DB_HOST = os.environ.get('DB_HOST', '')

if INSTANCE_CONNECTION_NAME:
    # Cloud Run - connect via Unix socket
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'stock_trading'),
            'USER': os.environ.get('DB_USER', 'samaanai_backend'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': f'/cloudsql/{INSTANCE_CONNECTION_NAME}',
            'PORT': '',
        }
    }
elif DB_HOST:
    # TCP connection (for local development with Cloud SQL Proxy)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'stock_trading'),
            'USER': os.environ.get('DB_USER', 'samaanai_backend'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': DB_HOST,
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }
else:
    # Build-time fallback - use SQLite (for collectstatic during Docker build)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }


# CORS - Production origins
CORS_ALLOWED_ORIGINS = [
    'https://stg.trading.samaanai.com',
    'https://trading.samaanai.com',
    'https://trading-dashboard-staging-hdp6ioqupa-uc.a.run.app',
    'https://trading-dashboard-staging-hdp6ioqupa-uw.a.run.app',
    'https://trading-dashboard-staging-362270100637.us-west1.run.app',
]
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://trading-.*\.run\.app$",
]


# Security settings for production
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'


# CSRF trusted origins
CSRF_TRUSTED_ORIGINS = [
    'https://stg.trading.samaanai.com',
    'https://trading.samaanai.com',
    'https://*.run.app',
]


# Static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# Logging for production
LOGGING['root']['level'] = 'INFO'
LOGGING['loggers']['django']['level'] = 'WARNING'

# OAuth Redirect URLs for production
# These are overridden from base.py for production environments
# The environment variable takes priority, with a sensible default for staging
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'https://trading-dashboard-staging-hdp6ioqupa-uc.a.run.app')
LOGIN_REDIRECT_URL = os.environ.get('LOGIN_REDIRECT_URL', f'{FRONTEND_URL}/auth/callback')
LOGOUT_REDIRECT_URL = os.environ.get('LOGOUT_REDIRECT_URL', f'{FRONTEND_URL}/')

print("🚀 Running with PRODUCTION settings")


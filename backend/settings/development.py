"""
Development settings for LLM Trading Agent project.
"""

from .base import *

DEBUG = True

# Development database - SQLite for easy local development
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Allow all hosts in development
ALLOWED_HOSTS = ['*']

# CORS - Allow all origins in development
CORS_ALLOW_ALL_ORIGINS = True

# Disable HTTPS requirements in development
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Additional development-only apps
INSTALLED_APPS += [
    'django_extensions',
]

# Simplified logging for development
LOGGING['root']['level'] = 'DEBUG'
LOGGING['loggers']['trading_api']['level'] = 'DEBUG'

print("🔧 Running with DEVELOPMENT settings")

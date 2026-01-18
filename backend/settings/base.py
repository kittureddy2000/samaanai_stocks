"""
Base Django settings for LLM Trading Agent project.

These settings are shared across development and production environments.
"""

import os
from pathlib import Path
from datetime import timedelta

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-secret-key-change-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    
    # Third-party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',  # Required for token blacklisting
    'corsheaders',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    
    # Local apps
    'trading_api',
]

SITE_ID = 1

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Custom User Model
AUTH_USER_MODEL = 'trading_api.User'


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler',
}

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}


# CORS Settings
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://localhost:5173',
    'http://127.0.0.1:3000',
]

CORS_ALLOW_CREDENTIALS = True


# Django Allauth Settings
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_VERIFICATION = 'optional'
ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https'

# OAuth redirect URLs - Frontend dashboard URL (configured via env var for different environments)
LOGIN_REDIRECT_URL = os.environ.get('LOGIN_REDIRECT_URL', 'http://localhost:3000/auth/callback')
LOGOUT_REDIRECT_URL = os.environ.get('LOGOUT_REDIRECT_URL', 'http://localhost:3000/')

# Social Account Settings
SOCIALACCOUNT_STORE_TOKENS = True
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

# Custom adapters for OAuth handling with JWT tokens
ACCOUNT_ADAPTER = 'trading_api.adapters.CustomAccountAdapter'
SOCIALACCOUNT_ADAPTER = 'trading_api.adapters.CustomSocialAccountAdapter'

# Google OAuth provider settings
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.environ.get('GOOGLE_CLIENT_ID', ''),
            'secret': os.environ.get('GOOGLE_CLIENT_SECRET', ''),
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    }
}


# Trading Configuration (migrated from config.py)
TRADING_CONFIG = {
    'ALPACA_API_KEY': os.environ.get('ALPACA_API_KEY', ''),
    'ALPACA_SECRET_KEY': os.environ.get('ALPACA_SECRET_KEY', ''),
    'ALPACA_BASE_URL': 'https://paper-api.alpaca.markets',
    'ALPACA_DATA_URL': 'https://data.alpaca.markets',
    
    'GEMINI_API_KEY': os.environ.get('GEMINI_API_KEY', ''),
    'GEMINI_MODEL': 'models/gemini-2.5-flash',
    'GEMINI_TEMPERATURE': 0.3,
    
    'NEWS_API_KEY': os.environ.get('NEWS_API_KEY', ''),
    
    'WATCHLIST': [
        # Tech Giants
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META',
        # AI & Semiconductors
        'NVDA', 'AMD', 'AVGO', 'TSM', 'MU',
        # Growth & Innovation
        'TSLA', 'NFLX', 'CRM', 'COIN', 'PLTR', 'CRWD',
        # Small Caps
        'IONQ', 'SOFI', 'RKLB', 'AFRM', 'UPST',
        # ETFs
        'ARKK', 'ICLN', 'XBI', 'BOTZ', 'SPY', 'QQQ',
    ],
    
    'STRATEGY': os.environ.get('TRADING_STRATEGY', 'balanced'),
    'ANALYSIS_INTERVAL_MINUTES': int(os.environ.get('ANALYSIS_INTERVAL', '15')),
    'MAX_POSITION_PCT': float(os.environ.get('MAX_POSITION_PCT', '0.10')),
    'MAX_DAILY_LOSS_PCT': float(os.environ.get('MAX_DAILY_LOSS_PCT', '0.03')),
    'MIN_CONFIDENCE': float(os.environ.get('MIN_CONFIDENCE', '0.70')),
    'STOP_LOSS_PCT': float(os.environ.get('STOP_LOSS_PCT', '0.05')),
    'TAKE_PROFIT_PCT': float(os.environ.get('TAKE_PROFIT_PCT', '0.10')),
}


# Slack Webhook (for trade notifications)
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL', '')


# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'trading_api': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

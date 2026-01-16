"""Django settings initialization."""

import os

# Default to development settings
env = os.environ.get('DJANGO_SETTINGS_MODULE', 'backend.settings.development')

if env == 'backend.settings.production':
    from .production import *
else:
    from .development import *

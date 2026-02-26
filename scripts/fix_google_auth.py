import os
import django
import sys

# Add the project root to the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings.production')
django.setup()

from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp
from urllib.parse import urlparse


def _infer_site_domain():
    """Infer backend site domain from env, preferring API host from ALLOWED_HOSTS."""
    allowed_hosts = os.environ.get('ALLOWED_HOSTS', '')
    for raw_host in allowed_hosts.split(','):
        host = (raw_host or '').strip()
        if not host or '*' in host:
            continue
        if host.startswith('.'):
            continue
        return host

    explicit = os.environ.get('SITE_DOMAIN', '').strip()
    if explicit:
        return explicit

    frontend_url = (os.environ.get('FRONTEND_URL') or '').strip()
    if frontend_url:
        parsed = urlparse(frontend_url)
        if parsed.hostname:
            return parsed.hostname

    return 'api.trading.samaanai.com'


def _remove_db_social_apps(provider: str):
    """
    Remove DB SocialApp rows for providers configured in settings.

    This project uses SOCIALACCOUNT_PROVIDERS['google']['APP'] in Django settings
    as the source of truth. Keeping DB SocialApp rows at the same time makes
    django-allauth see multiple app configs and raise MultipleObjectsReturned.
    """
    apps = list(SocialApp.objects.filter(provider=provider).order_by('id'))
    if not apps:
        print(f"   No DB SocialApp rows found for provider={provider}")
        return

    print(f"⚠️  Removing {len(apps)} DB SocialApp row(s) for provider={provider} to avoid allauth duplicate app resolution...")
    for app in apps:
        app_id = app.id
        app.delete()
        print(f"   Deleted SocialApp id={app_id}")

def setup_social_auth():
    print("🔧 Configuring Google Social Auth...")
    
    # 1. Configure Site
    # We use SITE_ID = 1 by default
    domain = _infer_site_domain()
    name = 'SamaanAI Trading'
    
    try:
        site = Site.objects.get(id=1)
        site.domain = domain
        site.name = name
        site.save()
        print(f"✅ Updated Site (id=1): {domain}")
    except Site.DoesNotExist:
        site = Site.objects.create(id=1, domain=domain, name=name)
        print(f"✅ Created Site (id=1): {domain}")

    # 2. Validate OAuth env vars (settings-based allauth provider config uses these)
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    
    if not client_id or not secret:
        print("⚠️  GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not found in env!")
        return

    provider = 'google'
    _remove_db_social_apps(provider)
    print("✅ Google OAuth app config will be read from Django settings env vars (GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET)")

if __name__ == '__main__':
    try:
        setup_social_auth()
    except Exception as e:
        print(f"❌ Error configuring social auth: {e}")
        sys.exit(1)

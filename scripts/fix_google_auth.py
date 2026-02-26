import os
import django
import sys

# Add the project root to the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings.production')
django.setup()

from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp
from django.conf import settings
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


def _dedupe_social_apps(provider: str):
    """Keep a single SocialApp for provider and delete duplicates."""
    apps = list(SocialApp.objects.filter(provider=provider).order_by('id'))
    if len(apps) <= 1:
        return apps[0] if apps else None

    primary = apps[0]
    print(f"⚠️  Found {len(apps)} SocialApp rows for provider={provider}; deduplicating...")
    for duplicate in apps[1:]:
        for site in duplicate.sites.all():
            primary.sites.add(site)
        duplicate.delete()
        print(f"   Deleted duplicate SocialApp id={duplicate.id}")
    return primary

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

    # 2. Configure SocialApp
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    
    if not client_id or not secret:
        print("⚠️  GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not found in env!")
        return

    provider = 'google'
    
    # Ensure we have only one app row for this provider.
    app = _dedupe_social_apps(provider)
    if app:
        app.client_id = client_id
        app.secret = secret
        app.name = 'Google Auth'
        app.save()
        print(f"✅ Updated existing SocialApp for {provider}")
    else:
        app = SocialApp.objects.create(
            provider=provider,
            name='Google Auth',
            client_id=client_id,
            secret=secret,
        )
        print(f"✅ Created new SocialApp for {provider}")
    
    # Link app to site
    if site not in app.sites.all():
        app.sites.add(site)
        print(f"✅ Linked SocialApp to Site: {domain}")
    else:
        print(f"   SocialApp already linked to Site: {domain}")

if __name__ == '__main__':
    try:
        setup_social_auth()
    except Exception as e:
        print(f"❌ Error configuring social auth: {e}")
        sys.exit(1)

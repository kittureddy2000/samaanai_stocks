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

def setup_social_auth():
    print("🔧 Configuring Google Social Auth...")
    
    # 1. Configure Site
    # We use SITE_ID = 1 by default
    domain = 'stg.trading.samaanai.com'
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
    
    # Check if app exists
    apps = SocialApp.objects.filter(provider=provider)
    if apps.exists():
        app = apps.first()
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

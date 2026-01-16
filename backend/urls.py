"""
URL configuration for LLM Trading Agent project.
"""

from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for Cloud Run."""
    return JsonResponse({'status': 'healthy', 'service': 'trading-api'})


urlpatterns = [
    # Health check (no auth required)
    path('health', health_check, name='health'),
    
    # Admin
    path('admin/', admin.site.urls),
    
    # Authentication
    path('auth/', include('trading_api.urls.auth')),
    
    # API endpoints
    path('api/', include('trading_api.urls.api')),
    
    # Django Allauth (for OAuth flows)
    path('accounts/', include('allauth.urls')),
]

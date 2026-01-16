"""Authentication URL configuration."""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from trading_api.views.auth import (
    RegisterView,
    LoginView,
    LogoutView,
    CurrentUserView,
    GoogleLoginCallbackView,
)

urlpatterns = [
    # Registration and login
    path('register', RegisterView.as_view(), name='auth-register'),
    path('login', LoginView.as_view(), name='auth-login'),
    path('logout', LogoutView.as_view(), name='auth-logout'),
    
    # Current user
    path('me', CurrentUserView.as_view(), name='auth-me'),
    
    # JWT token refresh
    path('token/refresh', TokenRefreshView.as_view(), name='token-refresh'),
    
    # Google OAuth callback
    path('google/callback', GoogleLoginCallbackView.as_view(), name='google-callback'),
]

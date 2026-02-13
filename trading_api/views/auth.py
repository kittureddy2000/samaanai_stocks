"""Authentication views.

Migrated from Flask to Django REST Framework.
Supports email/password and Google OAuth authentication.
"""

import re
import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

logger = logging.getLogger(__name__)
User = get_user_model()


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password: str) -> tuple:
    """Validate password strength."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    return True, ""


def get_tokens_for_user(user):
    """Generate JWT tokens for a user."""
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


class RegisterView(APIView):
    """Register a new user with email and password."""
    
    permission_classes = [AllowAny]
    
    def post(self, request):
        try:
            email = request.data.get('email', '').strip().lower()
            password = request.data.get('password', '')
            name = request.data.get('name', '').strip()
            
            # Validate email
            if not email or not validate_email(email):
                return Response(
                    {'error': 'Invalid email address'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate password
            valid, message = validate_password(password)
            if not valid:
                return Response(
                    {'error': message},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if user exists
            if User.objects.filter(email=email).exists():
                return Response(
                    {'error': 'Email already registered'},
                    status=status.HTTP_409_CONFLICT
                )
            
            # Create user
            user = User.objects.create_user(
                email=email,
                password=password,
                name=name or email.split('@')[0],
                auth_provider='local',
                is_active=True,
                email_verified=False
            )
            
            # Generate tokens
            tokens = get_tokens_for_user(user)
            
            logger.info(f"New user registered: {email}")
            
            return Response({
                'success': True,
                'message': 'Registration successful',
                'user': {
                    'email': user.email,
                    'name': user.name,
                    'authenticated': True,
                },
                'tokens': tokens,
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return Response(
                {'error': 'Registration failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class LoginView(APIView):
    """Login with email and password."""
    
    permission_classes = [AllowAny]
    
    def post(self, request):
        try:
            email = request.data.get('email', '').strip().lower()
            password = request.data.get('password', '')
            
            if not email or not password:
                return Response(
                    {'error': 'Email and password are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Find user
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                return Response(
                    {'error': 'Invalid email or password'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Check if user has a password
            if not user.has_usable_password():
                return Response(
                    {'error': 'This account uses Google Sign-In. Please sign in with Google.'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Verify password
            if not user.check_password(password):
                return Response(
                    {'error': 'Invalid email or password'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Check if account is active
            if not user.is_active:
                return Response(
                    {'error': 'Account is disabled'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Update last login
            user.update_last_login()
            
            # Generate tokens
            tokens = get_tokens_for_user(user)
            
            logger.info(f"User logged in: {email}")
            
            return Response({
                'success': True,
                'authenticated': True,
                'email': user.email,
                'name': user.name,
                'picture': user.picture_url,
                'tokens': tokens,
            })
            
        except Exception as e:
            logger.error(f"Login error: {e}")
            return Response(
                {'error': 'Login failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class LogoutView(APIView):
    """Logout the current user by blacklisting the refresh token."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Handle GET requests - logout and redirect to frontend."""
        self._do_logout_internal(request, refresh_token=None)
        # Redirect to frontend login page
        frontend_url = getattr(settings, 'FRONTEND_URL', 'https://trading.samaanai.com')
        return redirect(frontend_url)

    def post(self, request):
        """Handle POST requests with optional refresh token to blacklist."""
        refresh_token = request.data.get('refresh')
        return self._do_logout(request, refresh_token=refresh_token)

    def _do_logout_internal(self, request, refresh_token=None):
        """Perform logout without returning response."""
        try:
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except Exception as e:
            logger.error(f"Logout error: {e}")

    def _do_logout(self, request, refresh_token=None):
        """Perform logout - blacklist token if provided."""
        try:
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()

            return Response({'success': True, 'message': 'Logged out successfully'})

        except Exception as e:
            logger.error(f"Logout error: {e}")
            return Response({'success': True, 'message': 'Logged out'})


class CurrentUserView(APIView):
    """Get current authenticated user info."""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        return Response({
            'authenticated': True,
            'email': user.email,
            'name': user.name,
            'picture': user.picture_url,
            'auth_provider': user.auth_provider,
        })


class GoogleLoginCallbackView(APIView):
    """Handle Google OAuth callback."""
    
    permission_classes = [AllowAny]
    
    def post(self, request):
        """Process Google OAuth token and create/login user."""
        try:
            # Token from frontend (generated by Google One Tap or Sign In button)
            token = request.data.get('token')
            
            if not token:
                logger.error("Google login failed: No token provided")
                return Response(
                    {'error': 'No token provided'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Verify the token with Google
            try:
                # Specify the CLIENT_ID of the app that accesses the backend:
                client_id = settings.SOCIALACCOUNT_PROVIDERS['google']['APP']['client_id']
                id_info = id_token.verify_oauth2_token(
                    token, 
                    google_requests.Request(), 
                    client_id
                )

                # ID token is valid. Get the user's Google Account information from the decoded token.
                email = id_info.get('email', '').lower()
                name = id_info.get('name', '')
                picture = id_info.get('picture', '')
                
                # Check that the token was issued by Google
                if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                    raise ValueError('Wrong issuer.')

            except ValueError as e:
                # Invalid token
                logger.error(f"Google token verification failed: {str(e)}")
                return Response(
                    {'error': 'Invalid Google token'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            if not email:
                logger.error("Google login failed: No email in token")
                return Response(
                    {'error': 'Email not found in Google account'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get or create user
            try:
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'name': name,
                        'picture_url': picture,
                        'auth_provider': 'google',
                        'is_active': True,
                        'email_verified': True,
                    }
                )

                if not created:
                    # Update existing user
                    user.name = name or user.name
                    user.picture_url = picture
                    if user.auth_provider == 'local':
                        user.auth_provider = 'both'
                    user.update_last_login()
                    user.save()
                
                # Generate tokens
                tokens = get_tokens_for_user(user)
                
                logger.info(f"Google user {'created' if created else 'logged in'}: {email}")
                
                return Response({
                    'success': True,
                    'authenticated': True,
                    'email': user.email,
                    'name': user.name,
                    'picture': user.picture_url,
                    'tokens': tokens,
                })

            except Exception as e:
                # Database or other error during user saving
                logger.error(f"Error saving Google user {email}: {str(e)}")
                return Response(
                    {'error': 'Failed to save user account'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Exception as e:
            logger.error(f"Google OAuth callback unexpected error: {e}")
            return Response(
                {'error': 'Authentication failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

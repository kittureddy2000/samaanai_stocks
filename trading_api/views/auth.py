"""Authentication views.

Migrated from Flask to Django REST Framework.
Supports email/password and Google OAuth authentication.
"""

import re
import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

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
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
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
            # This would typically receive a token from the frontend
            # after the frontend has completed the Google OAuth flow
            google_token = request.data.get('token')
            user_info = request.data.get('user_info', {})
            
            email = user_info.get('email', '').lower()
            name = user_info.get('name', '')
            picture = user_info.get('picture', '')
            
            if not email:
                return Response(
                    {'error': 'Email is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get or create user
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
            logger.error(f"Google OAuth callback error: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

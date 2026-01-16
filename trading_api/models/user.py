"""User model for authentication and user management.

Migrated from SQLAlchemy to Django ORM.
"""

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


class UserManager(BaseUserManager):
    """Custom user manager for email-based authentication."""
    
    def create_user(self, email, password=None, **extra_fields):
        """Create and return a regular user."""
        if not email:
            raise ValueError('Users must have an email address')
        
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """Create and return a superuser."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('email_verified', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model for email-based authentication.
    
    Supports both email/password and Google OAuth authentication.
    """
    
    AUTH_PROVIDER_CHOICES = [
        ('local', 'Email/Password'),
        ('google', 'Google OAuth'),
        ('both', 'Both Methods'),
    ]
    
    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True)
    picture_url = models.URLField(max_length=500, blank=True)
    
    # Authentication provider
    auth_provider = models.CharField(
        max_length=50, 
        choices=AUTH_PROVIDER_CHOICES, 
        default='local'
    )
    
    # Account status
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # Email is already required as USERNAME_FIELD
    
    class Meta:
        db_table = 'users'
        verbose_name = 'user'
        verbose_name_plural = 'users'
    
    def __str__(self):
        return self.email
    
    def get_full_name(self):
        """Return the user's full name or email."""
        return self.name or self.email
    
    def get_short_name(self):
        """Return the user's name or email prefix."""
        return self.name or self.email.split('@')[0]
    
    def update_last_login(self):
        """Update the last login timestamp."""
        self.last_login = timezone.now()
        self.save(update_fields=['last_login'])

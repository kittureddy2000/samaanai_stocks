"""Django admin configuration for Trading API."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Trade, PortfolioSnapshot


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom User admin configuration."""
    
    list_display = ('email', 'name', 'auth_provider', 'is_active', 'is_staff', 'created_at')
    list_filter = ('is_active', 'is_staff', 'auth_provider', 'email_verified')
    search_fields = ('email', 'name')
    ordering = ('-created_at',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('name', 'picture_url')}),
        ('Authentication', {'fields': ('auth_provider', 'email_verified')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'created_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'name'),
        }),
    )
    
    readonly_fields = ('created_at', 'last_login')


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    """Trade admin configuration."""
    
    list_display = ('symbol', 'action', 'quantity', 'price', 'status', 'created_at')
    list_filter = ('action', 'status', 'order_type', 'created_at')
    search_fields = ('symbol', 'order_id')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)


@admin.register(PortfolioSnapshot)
class PortfolioSnapshotAdmin(admin.ModelAdmin):
    """Portfolio snapshot admin configuration."""
    
    list_display = ('portfolio_value', 'cash', 'equity', 'daily_change_pct', 'timestamp')
    list_filter = ('timestamp',)
    ordering = ('-timestamp',)
    readonly_fields = ('timestamp',)

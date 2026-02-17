"""Plaid integration models for read-only account/holding ingestion."""

from django.conf import settings
from django.db import models


class PlaidItem(models.Model):
    """Connected Plaid Item (one institution login)."""

    PRODUCT_CHOICES = [
        ('investments', 'Investments'),
        ('bank', 'Bank'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('login_required', 'Login Required'),
        ('error', 'Error'),
        ('disconnected', 'Disconnected'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='plaid_items',
    )
    item_id = models.CharField(max_length=128, unique=True, db_index=True)
    access_token = models.TextField()
    institution_id = models.CharField(max_length=128, blank=True, default='')
    institution_name = models.CharField(max_length=255, blank=True, default='')
    product_type = models.CharField(max_length=32, choices=PRODUCT_CHOICES)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='active', db_index=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default='')
    consent_expiration_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'plaid_items'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', 'product_type']),
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.institution_name or self.item_id}"


class PlaidAccount(models.Model):
    """Plaid account metadata and balances."""

    item = models.ForeignKey(
        PlaidItem,
        on_delete=models.CASCADE,
        related_name='accounts',
    )
    account_id = models.CharField(max_length=128, unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True, default='')
    official_name = models.CharField(max_length=255, blank=True, default='')
    mask = models.CharField(max_length=16, blank=True, default='')
    account_type = models.CharField(max_length=64, blank=True, default='')
    subtype = models.CharField(max_length=64, blank=True, default='')
    verification_status = models.CharField(max_length=64, blank=True, default='')
    current_balance = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    available_balance = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    limit_balance = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    iso_currency_code = models.CharField(max_length=8, blank=True, default='')
    unofficial_currency_code = models.CharField(max_length=16, blank=True, default='')
    raw = models.JSONField(default=dict, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'plaid_accounts'
        ordering = ['name', 'account_id']
        indexes = [
            models.Index(fields=['item', 'account_type']),
        ]

    def __str__(self):
        return f"{self.name or self.account_id}"


class PlaidSecurity(models.Model):
    """Investment security reference records."""

    item = models.ForeignKey(
        PlaidItem,
        on_delete=models.CASCADE,
        related_name='securities',
    )
    security_id = models.CharField(max_length=128, db_index=True)
    ticker_symbol = models.CharField(max_length=32, blank=True, default='')
    name = models.CharField(max_length=255, blank=True, default='')
    security_type = models.CharField(max_length=64, blank=True, default='')
    close_price = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    close_price_as_of = models.DateField(null=True, blank=True)
    iso_currency_code = models.CharField(max_length=8, blank=True, default='')
    unofficial_currency_code = models.CharField(max_length=16, blank=True, default='')
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'plaid_securities'
        ordering = ['ticker_symbol', 'security_id']
        constraints = [
            models.UniqueConstraint(fields=['item', 'security_id'], name='plaid_security_item_unique'),
        ]

    def __str__(self):
        return self.ticker_symbol or self.name or self.security_id


class PlaidHolding(models.Model):
    """Current holdings snapshot per account/security."""

    item = models.ForeignKey(
        PlaidItem,
        on_delete=models.CASCADE,
        related_name='holdings',
    )
    account = models.ForeignKey(
        PlaidAccount,
        on_delete=models.CASCADE,
        related_name='holdings',
    )
    security = models.ForeignKey(
        PlaidSecurity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='holdings',
    )
    quantity = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    institution_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    institution_value = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    cost_basis = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    iso_currency_code = models.CharField(max_length=8, blank=True, default='')
    unofficial_currency_code = models.CharField(max_length=16, blank=True, default='')
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'plaid_holdings'
        ordering = ['-institution_value', 'id']
        constraints = [
            models.UniqueConstraint(fields=['item', 'account', 'security'], name='plaid_holding_unique'),
        ]


class PlaidInvestmentTransaction(models.Model):
    """Investment transactions pulled from Plaid."""

    item = models.ForeignKey(
        PlaidItem,
        on_delete=models.CASCADE,
        related_name='investment_transactions',
    )
    account = models.ForeignKey(
        PlaidAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='investment_transactions',
    )
    security = models.ForeignKey(
        PlaidSecurity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='investment_transactions',
    )
    investment_transaction_id = models.CharField(max_length=128, unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True, default='')
    ticker_symbol = models.CharField(max_length=32, blank=True, default='')
    tx_type = models.CharField(max_length=64, blank=True, default='')
    subtype = models.CharField(max_length=64, blank=True, default='')
    amount = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    quantity = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    fees = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    date = models.DateField(null=True, blank=True, db_index=True)
    datetime = models.DateTimeField(null=True, blank=True)
    cancel_transaction_id = models.CharField(max_length=128, blank=True, default='')
    iso_currency_code = models.CharField(max_length=8, blank=True, default='')
    unofficial_currency_code = models.CharField(max_length=16, blank=True, default='')
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'plaid_investment_transactions'
        ordering = ['-date', '-updated_at']
        indexes = [
            models.Index(fields=['item', 'date']),
        ]


class PlaidSyncLog(models.Model):
    """Manual sync run diagnostics."""

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('error', 'Error'),
    ]

    item = models.ForeignKey(
        PlaidItem,
        on_delete=models.CASCADE,
        related_name='sync_logs',
        null=True,
        blank=True,
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='plaid_sync_logs',
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, db_index=True)
    message = models.TextField(blank=True, default='')
    accounts_synced = models.IntegerField(default=0)
    holdings_synced = models.IntegerField(default=0)
    transactions_synced = models.IntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'plaid_sync_logs'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['status', 'started_at']),
        ]


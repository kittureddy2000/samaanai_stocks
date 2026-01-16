"""Trade model for storing trade history.

Migrated from SQLAlchemy to Django ORM.
"""

from django.db import models
from django.conf import settings


class Trade(models.Model):
    """Trade model for recording executed trades."""
    
    ORDER_TYPE_CHOICES = [
        ('market', 'Market'),
        ('limit', 'Limit'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('executed', 'Executed'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
    ]
    
    ACTION_CHOICES = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trades'
    )
    
    # Trade details
    symbol = models.CharField(max_length=20, db_index=True)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=15, decimal_places=4)
    total_value = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Order details
    order_id = models.CharField(max_length=100, blank=True, null=True)
    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES, default='market')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='executed')
    
    # Risk management
    stop_loss = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    take_profit = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    
    # LLM analysis
    confidence = models.FloatField(null=True, blank=True)
    reasoning = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'trades'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['symbol', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.action} {self.quantity} {self.symbol} @ ${self.price}"


class PortfolioSnapshot(models.Model):
    """Portfolio snapshot for tracking portfolio value over time."""
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='portfolio_snapshots'
    )
    
    # Portfolio values
    portfolio_value = models.DecimalField(max_digits=15, decimal_places=2)
    cash = models.DecimalField(max_digits=15, decimal_places=2)
    equity = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Performance
    daily_change = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    daily_change_pct = models.FloatField(null=True, blank=True)
    
    # Timestamp
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'portfolio_snapshots'
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"${self.portfolio_value} @ {self.timestamp}"

"""Watchlist models for user-specific stock tracking."""

from django.db import models
from django.conf import settings


class WatchlistItem(models.Model):
    """Individual watchlist item for a user."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='watchlist_items'
    )
    symbol = models.CharField(max_length=10)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'symbol')
        ordering = ['symbol']

    def __str__(self):
        return f"{self.user.email}: {self.symbol}"

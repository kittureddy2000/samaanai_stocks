"""Trading API views package."""

from .auth import (
    RegisterView,
    LoginView,
    LogoutView,
    CurrentUserView,
    GoogleLoginCallbackView,
)

from .api import (
    PortfolioView,
    RiskView,
    MarketView,
    WatchlistView,
    TradesView,
    ConfigView,
    IndicatorsView,
    AnalyzeView,
)

__all__ = [
    # Auth views
    'RegisterView',
    'LoginView',
    'LogoutView',
    'CurrentUserView',
    'GoogleLoginCallbackView',
    # API views
    'PortfolioView',
    'RiskView',
    'MarketView',
    'WatchlistView',
    'TradesView',
    'ConfigView',
    'IndicatorsView',
    'AnalyzeView',
]

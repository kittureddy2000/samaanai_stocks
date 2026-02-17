"""API URL configuration for trading endpoints."""

from django.urls import path
from trading_api.views import api

urlpatterns = [
    # Broker connection status
    path('broker-status', api.BrokerStatusView.as_view(), name='api-broker-status'),

    # Portfolio and account
    path('portfolio', api.PortfolioView.as_view(), name='api-portfolio'),
    
    # Risk management
    path('risk', api.RiskView.as_view(), name='api-risk'),
    
    # Market status
    path('market', api.MarketView.as_view(), name='api-market'),
    
    # Watchlist
    path('watchlist', api.WatchlistView.as_view(), name='api-watchlist'),
    
    # Trade history
    path('trades', api.TradesView.as_view(), name='api-trades'),

    # Agent run health/history
    path('agent-status', api.AgentStatusView.as_view(), name='api-agent-status'),
    path('operations-summary', api.OperationsSummaryView.as_view(), name='api-operations-summary'),
    path('analyze-logs', api.AnalyzeLogsView.as_view(), name='api-analyze-logs'),

    # Plaid read-only integrations (manual sync only)
    path('plaid/overview', api.PlaidOverviewView.as_view(), name='api-plaid-overview'),
    path('plaid/link-token', api.PlaidLinkTokenView.as_view(), name='api-plaid-link-token'),
    path('plaid/exchange-token', api.PlaidExchangeTokenView.as_view(), name='api-plaid-exchange-token'),
    path('plaid/items/<int:item_id>/sync', api.PlaidItemSyncView.as_view(), name='api-plaid-item-sync'),
    path('plaid/items/<int:item_id>/disconnect', api.PlaidItemDisconnectView.as_view(), name='api-plaid-item-disconnect'),
    
    # Trading configuration
    path('config', api.ConfigView.as_view(), name='api-config'),
    
    # Technical indicators
    path('indicators', api.IndicatorsView.as_view(), name='api-indicators'),

    # Option chain data (public, uses yfinance)
    path('option-chain', api.OptionChainView.as_view(), name='api-option-chain'),

    # Collar strategy calculator (public, uses yfinance)
    path('collar-strategy', api.CollarStrategyView.as_view(), name='api-collar-strategy'),

    # Trigger analysis (for Cloud Scheduler)
    path('analyze', api.AnalyzeView.as_view(), name='api-analyze'),

    # Test trade endpoint (for testing trading functionality)
    path('test-trade', api.TestTradeView.as_view(), name='api-test-trade'),

    # Daily summary email (for Cloud Scheduler at market close)
    path('daily-summary', api.DailySummaryView.as_view(), name='api-daily-summary'),
]

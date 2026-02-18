"""Trading API views.

Migrated from Flask to Django REST Framework.
Includes trade/position persistence, DB fallback, and diagnostic logging.
"""

import logging
import os
import time
import threading
import csv
import re
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from django.conf import settings
from django.http import HttpResponse
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

logger = logging.getLogger(__name__)

# Small in-process cache to reduce yfinance rate-limit pressure.
_INDICATORS_CACHE_TTL_SECONDS = 60
_indicators_cache = {
    'timestamp': 0.0,
    'symbols': tuple(),
    'results': [],
}
_indicators_cache_lock = threading.Lock()

_POSITION_METRICS_CACHE_TTL_SECONDS = 300
_position_metrics_cache = {
    'timestamp': 0.0,
    'symbols': tuple(),
    'results': {},
}
_position_metrics_cache_lock = threading.Lock()

_MARKET_INDICES_CACHE_TTL_SECONDS = 30
_market_indices_cache = {
    'timestamp': 0.0,
    'results': {},
}
_market_indices_cache_lock = threading.Lock()

MARKET_INDEX_CONFIG = {
    'sp500': {'symbol': '^GSPC', 'label': 'S&P 500'},
    'nasdaq': {'symbol': '^IXIC', 'label': 'Nasdaq'},
    'vix': {'symbol': '^VIX', 'label': 'VIX'},
}

_OCC_OPTION_SYMBOL_RE = re.compile(r'^([A-Z]{1,6})\d{6}([CP])\d{8}$')

INDICATOR_LABELS = {
    'rsi': 'RSI',
    'macd': 'MACD',
    'moving_averages': 'Moving Averages',
    'bollinger_bands': 'Bollinger Bands',
    'volume': 'Volume',
    'price_action': 'Price Action',
    'vwap': 'VWAP',
    'atr': 'ATR',
}
DEFAULT_INDICATOR_SETTINGS = {key: True for key in INDICATOR_LABELS}


# ---------------------------------------------------------------------------
# Lazy import helpers
# ---------------------------------------------------------------------------

def get_trading_client():
    """Get trading client using broker factory (supports Alpaca and IBKR)."""
    from trading_api.services import get_broker
    return BrokerClientWrapper(get_broker())


def get_broker_info():
    """Get info about the current broker."""
    from trading_api.services import get_broker_name
    return get_broker_name()


class BrokerClientWrapper:
    """Wrapper to provide backward-compatible dict interface from broker dataclasses."""

    def __init__(self, broker):
        self.broker = broker

    def get_account(self):
        """Get account as dictionary."""
        account = self.broker.get_account()
        if not account:
            return None
        return {
            'id': account.id,
            'cash': account.cash,
            'buying_power': account.buying_power,
            'portfolio_value': account.portfolio_value,
            'equity': account.equity,
            'last_equity': account.last_equity,
        }

    def get_positions(self):
        """Get positions as list of dictionaries."""
        positions = self.broker.get_positions()
        return [
            {
                'symbol': pos.symbol,
                'qty': pos.qty,
                'avg_entry_price': pos.avg_entry_price,
                'current_price': pos.current_price,
                'market_value': pos.market_value,
                'unrealized_pl': pos.unrealized_pl,
                'unrealized_plpc': pos.unrealized_plpc,
            }
            for pos in positions
        ]

    def get_orders_history(self, limit=50):
        """Get order history as list of dictionaries."""
        orders = self.broker.get_orders_history(limit)
        return [
            {
                'id': order.id,
                'symbol': order.symbol,
                'side': order.side,
                'qty': order.qty,
                'type': order.order_type,
                'status': order.status,
                'limit_price': order.limit_price,
                'filled_qty': order.filled_qty,
                'filled_avg_price': order.filled_price,
                'created_at': str(order.created_at) if order.created_at else None,
            }
            for order in orders
        ]

    def is_market_open(self):
        """Check if market is open."""
        return self.broker.is_market_open()

    def get_market_hours(self):
        """Get market hours."""
        return self.broker.get_market_hours()


def get_risk_manager():
    """Get risk manager."""
    from trading_api.services import get_risk_manager as _get_rm
    RiskManager = _get_rm()
    return RiskManager()


def get_data_aggregator():
    """Get data aggregator."""
    from trading_api.services import get_data_aggregator as _get_da
    DataAggregator = _get_da()
    return DataAggregator()


def _normalize_indicator_settings(raw_settings) -> Dict[str, bool]:
    """Normalize indicator toggle payload to known keys."""
    normalized = dict(DEFAULT_INDICATOR_SETTINGS)
    if not isinstance(raw_settings, dict):
        return normalized
    for key in DEFAULT_INDICATOR_SETTINGS:
        if key in raw_settings:
            normalized[key] = bool(raw_settings[key])
    return normalized


def _effective_agent_settings():
    """Build effective runtime settings from defaults plus DB overrides."""
    trading_config = settings.TRADING_CONFIG
    effective = {
        'analysis_interval': int(trading_config['ANALYSIS_INTERVAL_MINUTES']),
        'max_position_pct': float(trading_config['MAX_POSITION_PCT']) * 100,
        'max_daily_loss_pct': float(trading_config['MAX_DAILY_LOSS_PCT']) * 100,
        'min_confidence': float(trading_config['MIN_CONFIDENCE']) * 100,
        'stop_loss_pct': float(trading_config['STOP_LOSS_PCT']) * 100,
        'take_profit_pct': float(trading_config['TAKE_PROFIT_PCT']) * 100,
        'indicator_settings': dict(DEFAULT_INDICATOR_SETTINGS),
    }

    try:
        from trading_api.models import AgentSettings
        persisted = AgentSettings.objects.filter(singleton_key='default').first()
        if persisted:
            effective.update({
                'analysis_interval': int(persisted.analysis_interval_minutes),
                'max_position_pct': float(persisted.max_position_pct) * 100,
                'max_daily_loss_pct': float(persisted.max_daily_loss_pct) * 100,
                'min_confidence': float(persisted.min_confidence) * 100,
                'stop_loss_pct': float(persisted.stop_loss_pct) * 100,
                'take_profit_pct': float(persisted.take_profit_pct) * 100,
                'indicator_settings': _normalize_indicator_settings(persisted.indicator_settings),
            })
    except Exception as exc:
        logger.warning(f"Agent settings unavailable, using defaults: {exc}")

    return effective


def apply_runtime_trading_settings():
    """Apply effective settings into src.config runtime object."""
    effective = _effective_agent_settings()
    try:
        from src.config import config as runtime_config
        runtime_config.trading.analysis_interval_minutes = int(effective['analysis_interval'])
        runtime_config.trading.max_position_pct = float(effective['max_position_pct']) / 100.0
        runtime_config.trading.max_daily_loss_pct = float(effective['max_daily_loss_pct']) / 100.0
        runtime_config.trading.min_confidence = float(effective['min_confidence']) / 100.0
        runtime_config.trading.default_stop_loss_pct = float(effective['stop_loss_pct']) / 100.0
        runtime_config.trading.default_take_profit_pct = float(effective['take_profit_pct']) / 100.0
        runtime_config.trading.enabled_indicators = _normalize_indicator_settings(
            effective.get('indicator_settings')
        )
    except Exception as exc:
        logger.warning(f"Failed to apply runtime trading settings: {exc}")
    return effective


def build_runtime_settings_snapshot(effective_settings):
    """Compact runtime settings snapshot for diagnostics/logging."""
    indicator_settings = _normalize_indicator_settings(
        effective_settings.get('indicator_settings')
    )
    enabled = [key for key, is_on in indicator_settings.items() if is_on]
    disabled = [key for key, is_on in indicator_settings.items() if not is_on]
    return {
        'analysis_interval': int(effective_settings.get('analysis_interval', 15)),
        'max_position_pct': float(effective_settings.get('max_position_pct', 10)),
        'max_daily_loss_pct': float(effective_settings.get('max_daily_loss_pct', 3)),
        'min_confidence': float(effective_settings.get('min_confidence', 70)),
        'stop_loss_pct': float(effective_settings.get('stop_loss_pct', 5)),
        'take_profit_pct': float(effective_settings.get('take_profit_pct', 10)),
        'indicators_enabled': enabled,
        'indicators_disabled': disabled,
    }


def _safe_float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN
        return None
    if result == float('inf') or result == float('-inf'):
        return None
    return result


def _as_local_date(value):
    """Best-effort conversion of broker timestamp values to local date."""
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        dt = parse_datetime(text.replace('Z', '+00:00'))
        if dt is None:
            try:
                dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
            except ValueError:
                return None

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_default_timezone())
    return timezone.localtime(dt).date()


def _count_today_executed_orders(orders):
    """Count filled/executed broker orders for current local date."""
    today = timezone.localdate()
    count = 0
    for order in orders or []:
        status = str(order.get('status', '')).lower()
        status = status.replace('orderstatus.', '').replace('order_status.', '')
        if status not in {'filled', 'executed'}:
            continue
        created_at = order.get('created_at')
        if _as_local_date(created_at) == today:
            count += 1
    return count


def get_market_indices_snapshot():
    """Fetch S&P 500, Nasdaq and VIX snapshot with short caching."""
    now = time.time()
    with _market_indices_cache_lock:
        age = now - _market_indices_cache['timestamp']
        if _market_indices_cache['results'] and age < _MARKET_INDICES_CACHE_TTL_SECONDS:
            return _market_indices_cache['results']

    results = {}
    try:
        import yfinance as yf
    except Exception as exc:
        logger.warning(f"Market indices fetch unavailable (yfinance import): {exc}")
        return results

    for key, cfg in MARKET_INDEX_CONFIG.items():
        symbol = cfg['symbol']
        label = cfg['label']
        price = None
        prev_close = None

        try:
            ticker = yf.Ticker(symbol)

            try:
                fast = getattr(ticker, 'fast_info', {}) or {}
                price = _safe_float(
                    fast.get('lastPrice')
                    or fast.get('last_price')
                    or fast.get('regularMarketPrice')
                )
                prev_close = _safe_float(
                    fast.get('previousClose')
                    or fast.get('previous_close')
                )
            except Exception:
                pass

            # Fallback to daily history if fast_info is unavailable.
            if price is None or prev_close is None:
                hist = ticker.history(period='5d', interval='1d', auto_adjust=False)
                if not hist.empty and 'Close' in hist.columns:
                    closes = hist['Close'].dropna()
                    if not closes.empty:
                        if price is None:
                            price = _safe_float(closes.iloc[-1])
                        if prev_close is None:
                            if len(closes) >= 2:
                                prev_close = _safe_float(closes.iloc[-2])
                            else:
                                prev_close = _safe_float(closes.iloc[-1])

            if price is None:
                continue

            change = None
            change_pct = None
            if prev_close not in (None, 0):
                change = price - prev_close
                change_pct = (change / prev_close) * 100

            results[key] = {
                'symbol': symbol,
                'label': label,
                'price': price,
                'change': change,
                'change_pct': change_pct,
            }
        except Exception as exc:
            logger.warning(f"Failed to fetch market index {symbol}: {exc}")

    with _market_indices_cache_lock:
        _market_indices_cache['timestamp'] = now
        _market_indices_cache['results'] = results
    return results


def _extract_close_series(downloaded, symbol, symbols):
    """Extract close-price series from yfinance download output."""
    try:
        import pandas as pd
    except Exception:
        return None

    if downloaded is None or getattr(downloaded, 'empty', True):
        return None

    try:
        if isinstance(downloaded.columns, pd.MultiIndex):
            if symbol not in downloaded.columns.get_level_values(0):
                return None
            df = downloaded[symbol]
        else:
            if len(symbols) != 1 or symbol != symbols[0]:
                return None
            df = downloaded
        close_series = df['Close'] if 'Close' in df.columns else None
        if close_series is None:
            return None
        close_series = close_series.dropna()
        return close_series if not close_series.empty else None
    except Exception:
        return None


def _get_position_market_metrics(symbols: List[str]) -> Dict[str, Dict]:
    """Fetch supplemental market metrics for portfolio symbols with caching."""
    clean_symbols = tuple(sorted({
        str(symbol).upper().strip()
        for symbol in (symbols or [])
        if symbol
    }))
    if not clean_symbols:
        return {}

    now = time.time()
    with _position_metrics_cache_lock:
        cache_hit = (
            _position_metrics_cache['results']
            and _position_metrics_cache['symbols'] == clean_symbols
            and (now - _position_metrics_cache['timestamp']) < _POSITION_METRICS_CACHE_TTL_SECONDS
        )
        if cache_hit:
            return dict(_position_metrics_cache['results'])

    defaults = {
        'day_change_pct': None,
        'ytd_return_pct': None,
        'week_52_high': None,
        'week_52_low': None,
        'from_52w_high_pct': None,
        'from_52w_low_pct': None,
        'forward_pe': None,
        'volatility_pct': None,
    }
    results = {symbol: dict(defaults) for symbol in clean_symbols}

    try:
        import yfinance as yf

        tickers = yf.Tickers(' '.join(clean_symbols))
        ytd_download = yf.download(
            tickers=' '.join(clean_symbols),
            period='ytd',
            interval='1d',
            group_by='ticker',
            auto_adjust=False,
            progress=False,
            threads=False,
        )

        for symbol in clean_symbols:
            metric = dict(defaults)
            ticker = tickers.tickers.get(symbol)
            info = {}
            fast_info = {}

            if ticker is not None:
                try:
                    info = ticker.info or {}
                except Exception:
                    info = {}
                try:
                    fast_info = dict(getattr(ticker, 'fast_info', {}) or {})
                except Exception:
                    fast_info = {}

            current_price = (
                _safe_float(fast_info.get('lastPrice'))
                or _safe_float(info.get('regularMarketPrice'))
                or _safe_float(info.get('currentPrice'))
            )
            prev_close = (
                _safe_float(fast_info.get('previousClose'))
                or _safe_float(info.get('regularMarketPreviousClose'))
            )
            if current_price is not None and prev_close and prev_close > 0:
                metric['day_change_pct'] = ((current_price - prev_close) / prev_close) * 100.0
            else:
                metric['day_change_pct'] = _safe_float(info.get('regularMarketChangePercent'))

            metric['week_52_high'] = (
                _safe_float(fast_info.get('yearHigh'))
                or _safe_float(info.get('fiftyTwoWeekHigh'))
            )
            metric['week_52_low'] = (
                _safe_float(fast_info.get('yearLow'))
                or _safe_float(info.get('fiftyTwoWeekLow'))
            )
            metric['forward_pe'] = _safe_float(info.get('forwardPE'))

            ytd_close = _extract_close_series(ytd_download, symbol, clean_symbols)
            if ytd_close is not None and len(ytd_close) >= 2:
                start_price = _safe_float(ytd_close.iloc[0])
                end_price = _safe_float(ytd_close.iloc[-1])
                if start_price and start_price > 0 and end_price is not None:
                    metric['ytd_return_pct'] = ((end_price - start_price) / start_price) * 100.0
                    if current_price is None:
                        current_price = end_price

                try:
                    daily_returns = ytd_close.pct_change().dropna()
                    if len(daily_returns) >= 5:
                        std = _safe_float(daily_returns.std())
                        if std is not None:
                            metric['volatility_pct'] = std * (252 ** 0.5) * 100.0
                except Exception:
                    pass

            if metric['week_52_high'] and metric['week_52_high'] > 0 and current_price is not None:
                metric['from_52w_high_pct'] = (
                    (current_price / metric['week_52_high']) - 1
                ) * 100.0
            if metric['week_52_low'] and metric['week_52_low'] > 0 and current_price is not None:
                metric['from_52w_low_pct'] = (
                    (current_price / metric['week_52_low']) - 1
                ) * 100.0

            results[symbol] = metric
    except Exception as exc:
        logger.warning(f"Position metrics enrichment unavailable, continuing without it: {exc}")

    with _position_metrics_cache_lock:
        _position_metrics_cache['timestamp'] = time.time()
        _position_metrics_cache['symbols'] = clean_symbols
        _position_metrics_cache['results'] = dict(results)

    return results


def _infer_option_type(symbol='', security_type='', security_name='', security_raw=None) -> str:
    """Infer option side (Call/Put) for Plaid holding rows."""
    raw = security_raw if isinstance(security_raw, dict) else {}
    raw_option = raw.get('option_contract') if isinstance(raw.get('option_contract'), dict) else {}

    for value in (
        raw_option.get('type'),
        raw_option.get('option_type'),
        raw.get('option_type'),
        raw.get('type'),
        security_type,
    ):
        token = str(value or '').strip().lower()
        if token == 'call':
            return 'Call'
        if token == 'put':
            return 'Put'

    clean_symbol = str(symbol or '').strip().upper().replace(' ', '')
    occ_match = _OCC_OPTION_SYMBOL_RE.match(clean_symbol)
    if occ_match:
        return 'Call' if occ_match.group(2) == 'C' else 'Put'

    text = f"{security_name or ''} {clean_symbol}".lower()
    if ' call' in f" {text}" or text.endswith('call'):
        return 'Call'
    if ' put' in f" {text}" or text.endswith('put'):
        return 'Put'
    return ''


def _resolve_metric_symbol(symbol='', security_type='', security_name='') -> str:
    """Resolve best symbol for market-metric lookup (underlying for options)."""
    clean_symbol = str(symbol or '').strip().upper().replace(' ', '')
    if not clean_symbol:
        return ''

    occ_match = _OCC_OPTION_SYMBOL_RE.match(clean_symbol)
    if occ_match:
        return occ_match.group(1)

    security_type_token = str(security_type or '').strip().lower()
    if 'option' in security_type_token or 'derivative' in security_type_token:
        name_match = re.search(r'\b([A-Z]{1,6})\b', str(security_name or '').upper())
        if name_match:
            return name_match.group(1)

    return clean_symbol


def _enrich_positions_with_market_metrics(positions: List[Dict]) -> List[Dict]:
    """Attach daily/YTD/52w metrics to each position row."""
    if not positions:
        return positions

    metrics_by_symbol = _get_position_market_metrics([p.get('symbol') for p in positions])
    enriched = []

    for pos in positions:
        symbol = str(pos.get('symbol') or '').upper()
        metrics = metrics_by_symbol.get(symbol, {})
        total_pl_pct = None
        raw_plpc = _safe_float(pos.get('unrealized_plpc'))
        if raw_plpc is not None:
            total_pl_pct = raw_plpc * 100.0

        row = dict(pos)
        row.update({
            'total_pl_pct': total_pl_pct,
            'day_change_pct': metrics.get('day_change_pct'),
            'ytd_return_pct': metrics.get('ytd_return_pct'),
            'week_52_high': metrics.get('week_52_high'),
            'week_52_low': metrics.get('week_52_low'),
            'from_52w_high_pct': metrics.get('from_52w_high_pct'),
            'from_52w_low_pct': metrics.get('from_52w_low_pct'),
        })
        enriched.append(row)

    return enriched


def classify_operational_issue(message='', llm_error=''):
    """Classify operational errors for dashboard/email rollups."""
    text = f"{message or ''} {llm_error or ''}".lower()

    gemini_rate_limit_keywords = (
        'rate limit', '429', 'quota', 'resource_exhausted', 'too many requests'
    )
    gemini_key_keywords = (
        'api key', 'api_key', 'invalid_api_key', 'api key not found', 'apikey not found'
    )
    gemini_keywords = (
        'gemini', 'generativelanguage.googleapis.com', 'googleapis.com'
    )
    ibkr_keywords = (
        'ibkr', 'gateway', 'not connected', 'connection refused', 'timed out',
        'timeout', 'socket', 'broken pipe', 'connection reset'
    )

    if any(k in text for k in gemini_rate_limit_keywords):
        return 'gemini_rate_limit'
    if any(k in text for k in gemini_key_keywords):
        return 'gemini_key'
    if any(k in text for k in gemini_keywords):
        return 'gemini_other'
    if any(k in text for k in ibkr_keywords):
        return 'ibkr_gateway'
    return 'other'


NON_EXECUTED_ORDER_STATUSES = {
    'rejected',
    'cancelled',
    'canceled',
    'inactive',
    'failed',
    'error',
    'api_error',
}


def normalize_order_status(status) -> str:
    """Normalize broker/order status text to lowercase token form."""
    value = str(status or '').strip().lower()
    value = value.replace('orderstatus.', '').replace('order_status.', '')
    return value.replace(' ', '_')


def is_countable_trade_record(record: Dict) -> bool:
    """Return True if the record should count as an executed/placed trade."""
    side = str(record.get('side') or record.get('action') or '').strip().upper()
    if side not in ('BUY', 'SELL'):
        return False

    status = normalize_order_status(record.get('status'))
    if status in NON_EXECUTED_ORDER_STATUSES:
        return False

    # Broker-generated orders should carry a stable id; treat missing id as
    # non-countable unless status clearly indicates a completed trade.
    order_id = record.get('id') or record.get('order_id')
    if order_id:
        return True

    return status in {'filled', 'executed', 'partially_filled', 'partial_fill'}


def count_countable_trades(records: List[Dict]) -> int:
    """Count trades that represent actual placed/executed orders."""
    return sum(1 for record in records if is_countable_trade_record(record or {}))


def count_db_trades_for_local_day(local_day) -> int:
    """Count countable trades in DB for a given local calendar day."""
    from trading_api.models import Trade

    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(local_day, datetime.min.time()), timezone=tz)
    end = start + timedelta(days=1)

    rows = Trade.objects.filter(created_at__gte=start, created_at__lt=end).values(
        'order_id', 'status', 'action'
    )
    return count_countable_trades(
        [
            {
                'order_id': row.get('order_id'),
                'status': row.get('status'),
                'action': row.get('action'),
            }
            for row in rows
        ]
    )


def build_operations_summary(days=14):
    """Build operations health summary for UI/email."""
    from trading_api.models.trade import AgentRunLog

    days = max(1, min(int(days or 14), 90))
    now = timezone.now()
    since = now - timedelta(days=days)

    effective_settings = apply_runtime_trading_settings()
    settings_snapshot = build_runtime_settings_snapshot(effective_settings)
    host, port, ibkr_connection = ConfigView._test_ibkr_connection()

    runs = list(
        AgentRunLog.objects.filter(created_at__gte=since)
        .order_by('-created_at')
        .values(
            'run_type', 'status', 'message', 'llm_ok', 'llm_error',
            'trades_recommended', 'trades_executed', 'created_at', 'details'
        )
    )

    day_keys = [
        (timezone.localdate(now - timedelta(days=offset))).isoformat()
        for offset in range(days - 1, -1, -1)
    ]
    per_day = {
        day_key: {
            'date': day_key,
            'analyze_runs': 0,
            'analyze_success': 0,
            'analyze_skipped': 0,
            'analyze_errors': 0,
            'llm_failures': 0,
            'trades_executed': 0,
            'ibkr_issues': 0,
            'gemini_rate_limit_issues': 0,
            'gemini_key_issues': 0,
            'gemini_other_issues': 0,
        }
        for day_key in day_keys
    }

    recent_events = []
    last_analyze_settings = None
    today_key = timezone.localdate(now).isoformat()

    for run in runs:
        run_day = timezone.localtime(run['created_at']).date().isoformat()
        if run_day not in per_day:
            continue

        bucket = per_day[run_day]
        run_type = run.get('run_type')
        status = (run.get('status') or '').lower()
        llm_ok = run.get('llm_ok')
        message = run.get('message') or ''
        llm_error = run.get('llm_error') or ''
        details = run.get('details') or {}

        if run_type == 'analyze':
            bucket['analyze_runs'] += 1
            if status == 'success':
                bucket['analyze_success'] += 1
            elif status == 'skipped':
                bucket['analyze_skipped'] += 1
            elif status in ('error', 'no_response'):
                bucket['analyze_errors'] += 1

            if llm_ok is False:
                bucket['llm_failures'] += 1

            if last_analyze_settings is None and isinstance(details, dict):
                last_analyze_settings = details.get('settings')

            bucket['trades_executed'] += int(run.get('trades_executed') or 0)

        issue_type = classify_operational_issue(message, llm_error)
        if issue_type == 'ibkr_gateway':
            bucket['ibkr_issues'] += 1
        elif issue_type == 'gemini_rate_limit':
            bucket['gemini_rate_limit_issues'] += 1
        elif issue_type == 'gemini_key':
            bucket['gemini_key_issues'] += 1
        elif issue_type == 'gemini_other':
            bucket['gemini_other_issues'] += 1

        if status in ('error', 'fallback', 'no_response'):
            recent_events.append({
                'time': timezone.localtime(run['created_at']).isoformat(),
                'run_type': run_type,
                'status': status,
                'issue_type': issue_type,
                'message': message or llm_error or 'Issue recorded',
            })

    today = per_day.get(today_key, next(iter(per_day.values())))

    # Reconcile today's trade count against persisted trade history so this
    # metric matches what users see in Trade History.
    try:
        trading_client = get_trading_client()
        broker_orders = trading_client.get_orders_history(limit=300)
        if broker_orders:
            sync_trades_to_db(broker_orders, user=None)
    except Exception as exc:
        logger.warning(f"Operations summary broker trade sync skipped: {exc}")

    try:
        db_trade_count_today = count_db_trades_for_local_day(timezone.localdate(now))
        if today_key in per_day:
            per_day[today_key]['trades_executed'] = db_trade_count_today
        today['trades_executed'] = db_trade_count_today
    except Exception as exc:
        logger.warning(f"Operations summary DB trade count unavailable: {exc}")

    has_gemini_key = bool(
        settings.TRADING_CONFIG.get('GEMINI_API_KEY')
        or os.environ.get('GEMINI_API_KEY')
    )

    return {
        'days': days,
        'generated_at': now.isoformat(),
        'checks': {
            'ibkr': {
                'host': host,
                'port': port,
                'tcp_status': ibkr_connection,
                'healthy': ibkr_connection == 'success',
            },
            'gemini': {
                'api_key_configured': has_gemini_key,
                'healthy_24h': (
                    today.get('gemini_key_issues', 0) == 0
                    and today.get('gemini_rate_limit_issues', 0) == 0
                    and today.get('gemini_other_issues', 0) == 0
                ),
            },
        },
        'effective_settings': settings_snapshot,
        'last_analyze_settings': last_analyze_settings or settings_snapshot,
        'today': today,
        'daily': [per_day[key] for key in day_keys],
        'recent_events': recent_events[:30],
    }


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def sync_trades_to_db(orders, user=None):
    """Sync IBKR trade data to Django Trade model.

    Uses order_id for deduplication via update_or_create.
    Only syncs orders that have an order_id.

    Args:
        orders: List of order dicts from BrokerClientWrapper.get_orders_history()
        user: Optional Django User instance

    Returns:
        Tuple of (created_count, updated_count)
    """
    from trading_api.models import Trade

    created = 0
    updated = 0

    for order in orders:
        order_id = order.get('id')
        if not order_id:
            continue

        side = order.get('side', '').upper()
        if side not in ('BUY', 'SELL'):
            continue

        qty = int(order.get('qty', 0)) if order.get('qty') else 0
        filled_price = order.get('filled_avg_price')
        price = filled_price or 0

        try:
            obj, was_created = Trade.objects.update_or_create(
                order_id=order_id,
                defaults={
                    'user': user,
                    'symbol': order.get('symbol', ''),
                    'action': side,
                    'quantity': qty,
                    'price': price,
                    'total_value': qty * float(price) if price else 0,
                    'order_type': order.get('type', 'market'),
                    'status': order.get('status', 'pending'),
                    'filled_qty': int(order.get('filled_qty', 0)) if order.get('filled_qty') else None,
                    'filled_avg_price': filled_price,
                    'limit_price': order.get('limit_price'),
                }
            )
            if was_created:
                created += 1
            else:
                updated += 1
        except Exception as e:
            logger.error(f"Failed to sync trade order_id={order_id}: {e}")

    if created or updated:
        logger.info(f"Trade sync complete: {created} created, {updated} updated")

    return created, updated


def save_portfolio_snapshot(account, positions, user=None):
    """Save portfolio and position snapshots to database.

    Args:
        account: Account dict from BrokerClientWrapper
        positions: List of position dicts
        user: Optional Django User instance

    Returns:
        The created PortfolioSnapshot, or None on error
    """
    from trading_api.models import PortfolioSnapshot, PositionSnapshot

    try:
        daily_change = account['equity'] - account['last_equity']
        daily_change_pct = (
            (daily_change / account['last_equity'] * 100)
            if account['last_equity'] > 0 else 0
        )

        snapshot = PortfolioSnapshot.objects.create(
            user=user,
            portfolio_value=account['portfolio_value'],
            cash=account['cash'],
            equity=account['equity'],
            daily_change=daily_change,
            daily_change_pct=daily_change_pct,
        )

        # Save individual positions linked to this snapshot
        for pos in positions:
            PositionSnapshot.objects.create(
                user=user,
                portfolio_snapshot=snapshot,
                symbol=pos['symbol'],
                qty=pos['qty'],
                avg_entry_price=pos['avg_entry_price'],
                current_price=pos['current_price'],
                market_value=pos['market_value'],
                unrealized_pl=pos['unrealized_pl'],
                unrealized_plpc=pos['unrealized_plpc'],
            )

        logger.info(
            f"Portfolio snapshot saved: ${account['portfolio_value']}, "
            f"{len(positions)} positions"
        )
        return snapshot

    except Exception as e:
        logger.error(f"Failed to save portfolio snapshot: {e}")
        return None


def record_agent_run(
    *,
    run_type,
    status,
    start_time=None,
    message='',
    duration_ms=None,
    market_open=None,
    llm_ok=None,
    llm_error='',
    trades_recommended=None,
    trades_executed=None,
    symbol=None,
    option_type=None,
    strike=None,
    recommendation_source=None,
    recommendation_candidates=None,
    details=None,
):
    """Persist run diagnostics to Cloud SQL without interrupting request flow."""
    from trading_api.models.trade import AgentRunLog

    try:
        resolved_duration_ms = duration_ms
        if resolved_duration_ms is None and start_time is not None:
            resolved_duration_ms = int(max(0, (time.time() - start_time) * 1000))

        AgentRunLog.objects.create(
            run_type=run_type,
            status=status,
            message=message or '',
            duration_ms=resolved_duration_ms,
            market_open=market_open,
            llm_ok=llm_ok,
            llm_error=llm_error or '',
            trades_recommended=trades_recommended,
            trades_executed=trades_executed,
            symbol=symbol,
            option_type=option_type,
            strike=strike,
            recommendation_source=recommendation_source,
            recommendation_candidates=recommendation_candidates,
            details=details or {},
        )
    except Exception as e:
        logger.error(f"Failed to record agent run log: {e}")


def should_save_snapshot(user):
    """Check if enough time has passed since last snapshot (5 min minimum)."""
    from trading_api.models import PortfolioSnapshot
    last = PortfolioSnapshot.objects.filter(user=user).order_by('-timestamp').first()
    if not last:
        return True
    return timezone.now() - last.timestamp > timedelta(minutes=5)


# ---------------------------------------------------------------------------
# API Views
# ---------------------------------------------------------------------------

class BrokerStatusView(APIView):
    """Get detailed broker connection status and diagnostics."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        import os
        import socket
        from datetime import datetime

        start_time = time.time()
        logger.info("BrokerStatusView.get called")

        broker_name = get_broker_info()
        host = os.environ.get('IBKR_GATEWAY_HOST', '127.0.0.1')
        port = int(os.environ.get('IBKR_GATEWAY_PORT', '4002'))

        status = {
            'broker': broker_name,
            'timestamp': datetime.now().isoformat(),
            'gateway': {
                'host': host,
                'port': port,
            },
            'checks': {},
            'errors': [],
        }

        # Check 1: TCP connectivity to IBKR Gateway
        try:
            tcp_start = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            tcp_elapsed = time.time() - tcp_start

            if result == 0:
                status['checks']['tcp_connection'] = {
                    'status': 'ok',
                    'message': f'TCP connection to {host}:{port} successful ({tcp_elapsed:.2f}s)'
                }
                logger.info(f"BrokerStatus TCP check OK: {host}:{port} in {tcp_elapsed:.2f}s")
            else:
                status['checks']['tcp_connection'] = {
                    'status': 'error',
                    'message': f'TCP connection failed (code={result}, {tcp_elapsed:.2f}s)'
                }
                status['errors'].append(f'Cannot reach IBKR Gateway at {host}:{port}')
                logger.warning(f"BrokerStatus TCP check FAILED: code={result}, {tcp_elapsed:.2f}s")
        except Exception as e:
            status['checks']['tcp_connection'] = {
                'status': 'error',
                'message': str(e)
            }
            status['errors'].append(f'TCP connection error: {str(e)}')
            logger.error(f"BrokerStatus TCP exception: {e}")

        # Check 2: Broker API connection
        try:
            api_start = time.time()
            from trading_api.services import get_broker
            broker = get_broker()

            if broker.test_connection():
                api_elapsed = time.time() - api_start
                status['checks']['api_connection'] = {
                    'status': 'ok',
                    'message': f'IBKR API connection verified ({api_elapsed:.2f}s)'
                }
                logger.info(f"BrokerStatus API check OK in {api_elapsed:.2f}s")
            else:
                api_elapsed = time.time() - api_start
                status['checks']['api_connection'] = {
                    'status': 'error',
                    'message': f'IBKR API connection test failed ({api_elapsed:.2f}s)'
                }
                status['errors'].append('Broker API connection test failed')
                logger.warning(f"BrokerStatus API check FAILED in {api_elapsed:.2f}s")
        except Exception as e:
            status['checks']['api_connection'] = {
                'status': 'error',
                'message': str(e)
            }
            status['errors'].append(f'Broker API error: {str(e)}')
            logger.error(f"BrokerStatus API exception: {e}")

        # Check 3: Account data retrieval
        try:
            acct_start = time.time()
            trading_client = get_trading_client()
            account = trading_client.get_account()
            acct_elapsed = time.time() - acct_start

            if account:
                status['checks']['account_data'] = {
                    'status': 'ok',
                    'message': f'Account {account.get("id", "unknown")} accessible ({acct_elapsed:.2f}s)',
                    'account_id': account.get('id'),
                    'cash': account.get('cash'),
                    'portfolio_value': account.get('portfolio_value'),
                    'buying_power': account.get('buying_power'),
                }
                status['trading_ready'] = True
                logger.info(
                    f"BrokerStatus account check OK in {acct_elapsed:.2f}s: "
                    f"account={account.get('id')}"
                )
            else:
                status['checks']['account_data'] = {
                    'status': 'error',
                    'message': f'Failed to retrieve account data ({acct_elapsed:.2f}s)'
                }
                status['errors'].append('Cannot retrieve account data from broker')
                status['trading_ready'] = False
                logger.warning(f"BrokerStatus account check FAILED in {acct_elapsed:.2f}s")
        except Exception as e:
            status['checks']['account_data'] = {
                'status': 'error',
                'message': str(e)
            }
            status['errors'].append(f'Account data error: {str(e)}')
            status['trading_ready'] = False
            logger.error(f"BrokerStatus account exception: {e}")

        # Overall status
        all_checks_ok = all(
            check.get('status') == 'ok'
            for check in status['checks'].values()
        )
        status['overall_status'] = 'connected' if all_checks_ok else 'error'
        status['can_trade'] = all_checks_ok and status.get('trading_ready', False)

        elapsed = time.time() - start_time
        check_summary = ', '.join(
            f'{k}:{v.get("status")}' for k, v in status['checks'].items()
        )
        logger.info(
            f"BrokerStatusView.get completed in {elapsed:.2f}s: "
            f"overall={status['overall_status']}, can_trade={status['can_trade']}, "
            f"checks=[{check_summary}]"
        )

        return Response(status)


class PortfolioView(APIView):
    """Get current portfolio data with persistence and fallback."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_time = time.time()
        logger.info("PortfolioView.get called")

        try:
            trading_client = get_trading_client()
            account = trading_client.get_account()
            positions = trading_client.get_positions()
            positions = _enrich_positions_with_market_metrics(positions)

            if not account:
                logger.warning("PortfolioView: account data unavailable, falling back to DB")
                return self._fallback_from_db(request)

            # Get previous day's equity from DB snapshots for accurate daily change
            from trading_api.models import PortfolioSnapshot
            user = request.user if request.user.is_authenticated else None
            today = timezone.now().date()

            # Find the most recent snapshot from before today (previous trading day)
            prev_snapshot = PortfolioSnapshot.objects.filter(
                user=user,
                timestamp__date__lt=today
            ).order_by('-timestamp').first()

            if prev_snapshot:
                last_equity = float(prev_snapshot.equity)
                logger.debug(f"Using previous snapshot equity: ${last_equity} from {prev_snapshot.timestamp}")
            else:
                # Fallback to broker's last_equity if no previous snapshot
                last_equity = account['last_equity']
                logger.debug(f"No previous snapshot, using broker last_equity: ${last_equity}")

            daily_change = account['equity'] - last_equity
            daily_change_pct = (
                (daily_change / last_equity * 100)
                if last_equity > 0 else 0
            )
            import os
            initial_capital = float(
                os.environ.get(
                    'INITIAL_CAPITAL',
                    settings.TRADING_CONFIG.get('INITIAL_CAPITAL', 1_000_000)
                )
            )
            portfolio_value = float(account['portfolio_value'])
            overall_change = portfolio_value - initial_capital
            overall_change_pct = (
                (overall_change / initial_capital * 100)
                if initial_capital > 0 else 0
            )

            # Persist snapshot (rate limited)
            if should_save_snapshot(user):
                save_portfolio_snapshot(account, positions, user=user)

            elapsed = time.time() - start_time
            logger.info(
                f"PortfolioView.get completed in {elapsed:.2f}s: "
                f"portfolio=${account['portfolio_value']}, "
                f"{len(positions)} positions"
            )

            return Response({
                'account': {
                    'cash': account['cash'],
                    'portfolio_value': account['portfolio_value'],
                    'equity': account['equity'],
                    'buying_power': account['buying_power'],
                    'initial_capital': initial_capital,
                },
                'performance': {
                    'daily_change': daily_change,
                    'daily_change_pct': daily_change_pct,
                    'overall_change': overall_change,
                    'overall_change_pct': overall_change_pct,
                },
                'positions': positions,
                'positions_count': len(positions),
                'broker_connected': True,
                'source': 'ibkr_live',
            })
        except Exception as e:
            elapsed = time.time() - start_time
            logger.warning(
                f"PortfolioView.get broker failed in {elapsed:.2f}s: {e}, "
                f"falling back to DB"
            )
            return self._fallback_from_db(request)

    def _fallback_from_db(self, request):
        """Serve portfolio from most recent DB snapshot."""
        from trading_api.models import PortfolioSnapshot

        snapshot = PortfolioSnapshot.objects.filter(
            user=request.user
        ).order_by('-timestamp').first()

        if not snapshot:
            logger.info("PortfolioView fallback: no snapshots in DB")
            return Response({
                'account': {'cash': 0, 'portfolio_value': 0, 'equity': 0, 'buying_power': 0},
                'performance': {'daily_change': 0, 'daily_change_pct': 0},
                'positions': [],
                'positions_count': 0,
                'broker_connected': False,
                'source': 'none',
                'error': 'No data available - broker disconnected and no snapshots saved',
            })

        positions = []
        for ps in snapshot.positions.all():
            positions.append({
                'symbol': ps.symbol,
                'qty': float(ps.qty),
                'avg_entry_price': float(ps.avg_entry_price),
                'current_price': float(ps.current_price),
                'market_value': float(ps.market_value),
                'unrealized_pl': float(ps.unrealized_pl),
                'unrealized_plpc': float(ps.unrealized_plpc),
            })
        positions = _enrich_positions_with_market_metrics(positions)

        logger.info(
            f"PortfolioView fallback from DB: "
            f"snapshot={snapshot.timestamp.isoformat()}, {len(positions)} positions"
        )

        import os
        initial_capital = float(
            os.environ.get(
                'INITIAL_CAPITAL',
                settings.TRADING_CONFIG.get('INITIAL_CAPITAL', 1_000_000)
            )
        )
        portfolio_value = float(snapshot.portfolio_value)
        overall_change = portfolio_value - initial_capital
        overall_change_pct = (
            (overall_change / initial_capital * 100)
            if initial_capital > 0 else 0
        )

        return Response({
            'account': {
                'cash': float(snapshot.cash),
                'portfolio_value': float(snapshot.portfolio_value),
                'equity': float(snapshot.equity),
                'buying_power': 0,
                'initial_capital': initial_capital,
            },
            'performance': {
                'daily_change': float(snapshot.daily_change or 0),
                'daily_change_pct': float(snapshot.daily_change_pct or 0),
                'overall_change': overall_change,
                'overall_change_pct': overall_change_pct,
            },
            'positions': positions,
            'positions_count': len(positions),
            'broker_connected': False,
            'source': 'database',
            'snapshot_time': snapshot.timestamp.isoformat(),
        })


class RiskView(APIView):
    """Get current risk status."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_time = time.time()
        logger.info("RiskView.get called")
        try:
            from trading_api.models import Trade

            trading_client = get_trading_client()
            apply_runtime_trading_settings()
            risk_manager = get_risk_manager()

            account = trading_client.get_account()
            if not account:
                elapsed = time.time() - start_time
                logger.warning(f"RiskView.get: account unavailable ({elapsed:.2f}s)")
                return Response({
                    'risk_level': 'UNKNOWN',
                    'daily_trades': 0,
                    'daily_loss': 0,
                    'max_position_value': 0,
                    'kill_switch_active': False,
                    'broker_connected': False,
                    'market_indices': get_market_indices_snapshot(),
                    'error': 'Broker not connected',
                })

            risk_status = risk_manager.get_risk_status(account)
            risk_status['broker_connected'] = True

            # Daily trade counts should not rely on in-memory counters only.
            today = timezone.localdate()
            daily_trades_db = Trade.objects.filter(
                Q(executed_at__date=today) | Q(executed_at__isnull=True, created_at__date=today),
                status__in=['filled', 'executed'],
            ).count()

            daily_trades_broker = 0
            try:
                orders = trading_client.get_orders_history(limit=300)
                if orders:
                    sync_trades_to_db(orders, user=request.user)
                daily_trades_broker = _count_today_executed_orders(orders)
            except Exception as broker_exc:
                logger.warning(f"RiskView.get broker order count failed: {broker_exc}")

            risk_status['daily_trades'] = max(
                int(risk_status.get('daily_trades') or 0),
                int(daily_trades_db or 0),
                int(daily_trades_broker or 0),
            )
            risk_status['market_indices'] = get_market_indices_snapshot()

            elapsed = time.time() - start_time
            logger.info(
                f"RiskView.get completed in {elapsed:.2f}s: "
                f"risk_level={risk_status.get('risk_level', 'N/A')}"
            )
            return Response(risk_status)
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"RiskView.get failed in {elapsed:.2f}s: {e}")
            return Response({
                'risk_level': 'UNKNOWN',
                'daily_trades': 0,
                'daily_loss': 0,
                'max_position_value': 0,
                'kill_switch_active': False,
                'broker_connected': False,
                'market_indices': get_market_indices_snapshot(),
                'error': str(e),
            })


class MarketView(APIView):
    """Get market status."""

    permission_classes = [AllowAny]  # Public endpoint

    def get(self, request):
        start_time = time.time()
        logger.debug("MarketView.get called")
        try:
            trading_client = get_trading_client()
            is_open = trading_client.is_market_open()
            hours = trading_client.get_market_hours()

            elapsed = time.time() - start_time
            logger.debug(f"MarketView.get completed in {elapsed:.2f}s: is_open={is_open}")

            response = Response({
                'is_open': is_open,
                'next_open': hours.get('next_open') if hours else None,
                'next_close': hours.get('next_close') if hours else None,
                'broker_connected': True,
            })
            # Prevent caching of market status
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response
        except Exception as e:
            elapsed = time.time() - start_time
            logger.warning(f"MarketView.get failed in {elapsed:.2f}s: {e}")
            from datetime import datetime
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo('America/New_York'))

            # Skip weekends
            if now.weekday() >= 5:
                is_market_hours = False
            else:
                # Proper market hours: 9:30 AM - 4:00 PM ET
                market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
                market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
                is_market_hours = market_open <= now < market_close

            response = Response({
                'is_open': is_market_hours,
                'next_open': None,
                'next_close': None,
                'broker_connected': False,
                'error': str(e),
            })
            # Prevent caching of market status
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response


class WatchlistView(APIView):
    """Manage user watchlist with add/delete functionality."""

    permission_classes = [IsAuthenticated]

    def _get_watchlist_symbols(self, user):
        """Get user's watchlist symbols or default if none exists."""
        try:
            from trading_api.models.watchlist import WatchlistItem
            user_items = WatchlistItem.objects.filter(user=user)
            if user_items.exists():
                return list(user_items.values_list('symbol', flat=True)), True
        except Exception as e:
            logger.warning(f"Watchlist model/table unavailable, using defaults: {e}")
        return settings.TRADING_CONFIG['WATCHLIST'], False

    def get(self, request):
        start_time = time.time()
        logger.info("WatchlistView.get called")
        try:
            import yfinance as yf

            watchlist_symbols, is_custom = self._get_watchlist_symbols(request.user)

            tickers = yf.Tickers(' '.join(watchlist_symbols))
            watchlist = []
            for symbol in watchlist_symbols:
                try:
                    ticker = tickers.tickers.get(symbol)
                    info = ticker.info if ticker else {}
                    price = info.get('regularMarketPrice') or info.get('currentPrice') or 0
                    prev_close = info.get('regularMarketPreviousClose') or 0
                    change = info.get('regularMarketChange') or (
                        price - prev_close if prev_close else 0
                    )
                    change_pct = info.get('regularMarketChangePercent') or (
                        (change / prev_close * 100) if prev_close > 0 else 0
                    )
                    watchlist.append({
                        'symbol': symbol,
                        'price': float(price),
                        'change': round(float(change), 2),
                        'change_pct': round(float(change_pct), 2),
                        'prev_close': float(prev_close),
                        'volume': int(info.get('regularMarketVolume') or 0),
                        'market_cap': int(info.get('marketCap') or 0),
                    })
                except Exception as e:
                    logger.debug(f"WatchlistView: error fetching {symbol}: {e}")
                    watchlist.append({
                        'symbol': symbol, 'price': 0, 'change': 0,
                        'change_pct': 0, 'prev_close': 0, 'volume': 0,
                        'market_cap': 0,
                    })

            elapsed = time.time() - start_time
            logger.info(
                f"WatchlistView.get completed in {elapsed:.2f}s: "
                f"{len(watchlist)} symbols (custom={is_custom})"
            )
            return Response({'watchlist': watchlist, 'is_custom': is_custom})
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"WatchlistView.get failed in {elapsed:.2f}s: {e}")
            watchlist_symbols, _ = self._get_watchlist_symbols(request.user)
            return Response({
                'watchlist': [{
                    'symbol': s, 'price': 0, 'change': 0, 'change_pct': 0,
                    'prev_close': 0, 'volume': 0, 'market_cap': 0,
                } for s in watchlist_symbols],
                'error': str(e),
            })

    def post(self, request):
        """Add a symbol to user's watchlist."""
        start_time = time.time()
        try:
            from trading_api.models.watchlist import WatchlistItem
        except Exception as e:
            logger.error(f"WatchlistView.post model import failed: {e}")
            return Response({'error': 'Watchlist service unavailable'}, status=503)

        symbol = request.data.get('symbol', '').upper().strip()
        if not symbol:
            return Response({'error': 'symbol is required'}, status=400)
        if len(symbol) > 10 or not symbol.isalpha():
            return Response({'error': 'Invalid symbol format'}, status=400)

        # If user has no custom watchlist yet, seed with defaults first
        if not WatchlistItem.objects.filter(user=request.user).exists():
            for s in settings.TRADING_CONFIG['WATCHLIST']:
                WatchlistItem.objects.get_or_create(user=request.user, symbol=s)
            logger.info(f"WatchlistView.post: seeded default watchlist for {request.user.email}")

        item, created = WatchlistItem.objects.get_or_create(
            user=request.user, symbol=symbol
        )

        elapsed = time.time() - start_time
        logger.info(
            f"WatchlistView.post completed in {elapsed:.2f}s: "
            f"{symbol} {'added' if created else 'already exists'}"
        )

        return Response({
            'success': True,
            'symbol': symbol,
            'created': created,
            'message': f'{symbol} added to watchlist' if created else f'{symbol} already in watchlist'
        })

    def delete(self, request):
        """Remove a symbol from user's watchlist."""
        start_time = time.time()
        try:
            from trading_api.models.watchlist import WatchlistItem
        except Exception as e:
            logger.error(f"WatchlistView.delete model import failed: {e}")
            return Response({'error': 'Watchlist service unavailable'}, status=503)

        symbol = request.data.get('symbol', '').upper().strip()
        if not symbol:
            return Response({'error': 'symbol is required'}, status=400)

        deleted, _ = WatchlistItem.objects.filter(
            user=request.user, symbol=symbol
        ).delete()

        elapsed = time.time() - start_time
        logger.info(
            f"WatchlistView.delete completed in {elapsed:.2f}s: "
            f"{symbol} {'removed' if deleted else 'not found'}"
        )

        return Response({
            'success': deleted > 0,
            'symbol': symbol,
            'message': f'{symbol} removed from watchlist' if deleted else f'{symbol} not in watchlist'
        })


class TradesView(APIView):
    """Get recent trade history, with DB persistence and fallback."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_time = time.time()
        logger.info("TradesView.get called")

        # Get pagination params with defaults
        page = int(request.query_params.get('page', 1))
        limit = int(request.query_params.get('limit', 50))
        limit = min(limit, 200)  # Cap at 200 max per request
        offset = (page - 1) * limit

        user = request.user if request.user.is_authenticated else None
        broker_connected = False
        broker_trades = []

        # Try to get live trades from broker
        try:
            trading_client = get_trading_client()
            orders = trading_client.get_orders_history(limit=100)  # Increased from 30
            broker_connected = True

            # Sync live trades to DB for persistence
            if orders:
                sync_trades_to_db(orders, user=user)

            for order in orders:
                qty = order.get('qty', 0)
                filled_qty = order.get('filled_qty', 0)

                broker_trades.append({
                    'id': order.get('id'),
                    'symbol': order.get('symbol'),
                    'action': order.get('side', '').upper(),
                    'quantity': int(qty) if qty else 0,
                    'filled_quantity': int(filled_qty) if filled_qty else 0,
                    'order_type': order.get('type', '').replace('OrderType.', '').replace('order_type.', ''),
                    'status': order.get('status', '').replace('OrderStatus.', '').replace('order_status.', ''),
                    'limit_price': order.get('limit_price'),
                    'filled_price': order.get('filled_avg_price'),
                    'created_at': order.get('created_at'),
                })
        except Exception as e:
            logger.warning(f"TradesView.get broker error: {e}")

        # Always supplement with DB trades (covers gateway restarts)
        db_trades = self._get_db_trades(user)

        # Merge: broker trades first, then DB trades not already in broker set
        broker_ids = {t['id'] for t in broker_trades if t.get('id')}
        merged_trades = list(broker_trades)
        for t in db_trades:
            if t['id'] not in broker_ids:
                merged_trades.append(t)

        # Sort by created_at descending
        merged_trades.sort(
            key=lambda t: t.get('created_at') or '', reverse=True
        )

        # Apply pagination
        total_count = len(merged_trades)
        paginated_trades = merged_trades[offset:offset + limit]

        source = 'ibkr_live' if broker_trades else ('database' if db_trades else 'none')

        elapsed = time.time() - start_time
        logger.info(
            f"TradesView.get completed in {elapsed:.2f}s: "
            f"{len(broker_trades)} from broker + {len(db_trades)} from DB "
            f"= {total_count} total, returning {len(paginated_trades)} (page {page})"
        )

        return Response({
            'trades': paginated_trades,
            'broker_connected': broker_connected,
            'source': source,
            'total': total_count,
            'page': page,
            'limit': limit,
            'has_more': offset + limit < total_count,
        })

    def _get_db_trades(self, user):
        """Get trade history from the Django database.

        Fetches trades for the current user AND trades with no user (synced
        before authentication or from background tasks). This ensures trades
        are never lost due to user mismatch.
        """
        from trading_api.models import Trade
        from django.db.models import Q

        # Get trades for this user OR trades with no user assigned
        if user:
            trade_filter = Q(user=user) | Q(user__isnull=True)
        else:
            trade_filter = Q(user__isnull=True)

        db_trades = Trade.objects.filter(
            trade_filter
        ).order_by('-created_at')[:500]  # Increased from 50 to support pagination

        logger.debug(f"_get_db_trades: found {len(db_trades)} trades in DB (user={user})")

        trades = []
        for t in db_trades:
            trades.append({
                'id': t.order_id or str(t.id),
                'symbol': t.symbol,
                'action': t.action,
                'quantity': t.quantity,
                'filled_quantity': t.filled_qty or 0,
                'order_type': t.order_type,
                'status': t.status,
                'limit_price': float(t.limit_price) if t.limit_price else None,
                'filled_price': float(t.filled_avg_price) if t.filled_avg_price else None,
                'created_at': t.created_at.isoformat() if t.created_at else None,
            })

        return trades


class AgentStatusView(APIView):
    """Operational health for scheduler runs, LLM, and trade execution."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def _serialize_run(run):
        if not run:
            return None
        return {
            'id': run.id,
            'run_type': run.run_type,
            'status': run.status,
            'message': run.message,
            'duration_ms': run.duration_ms,
            'market_open': run.market_open,
            'llm_ok': run.llm_ok,
            'llm_error': run.llm_error,
            'trades_recommended': run.trades_recommended,
            'trades_executed': run.trades_executed,
            'symbol': run.symbol,
            'option_type': run.option_type,
            'strike': float(run.strike) if run.strike is not None else None,
            'recommendation_source': run.recommendation_source,
            'recommendation_candidates': run.recommendation_candidates,
            'created_at': run.created_at.isoformat() if run.created_at else None,
        }

    def get(self, request):
        start_time = time.time()
        logger.info("AgentStatusView.get called")

        try:
            from django.db.models import Count, Sum, Q
            from trading_api.models.trade import AgentRunLog

            now = timezone.now()
            since_24h = now - timedelta(hours=24)

            analyze_qs = AgentRunLog.objects.filter(run_type='analyze')
            recent_qs = analyze_qs.order_by('-created_at')
            last_run = recent_qs.first()
            last_trade_run = recent_qs.filter(trades_executed__gt=0).first()
            last_llm_issue = AgentRunLog.objects.filter(
                run_type__in=['analyze', 'option_chain'],
                llm_ok=False
            ).order_by('-created_at').first()

            stats_24h = analyze_qs.filter(created_at__gte=since_24h).aggregate(
                runs=Count('id'),
                success_runs=Count('id', filter=Q(status='success')),
                no_trade_runs=Count('id', filter=Q(status='no_trades')),
                skipped_runs=Count('id', filter=Q(status='skipped')),
                error_runs=Count('id', filter=Q(status='error')),
                no_response_runs=Count('id', filter=Q(status='no_response')),
                llm_failures=Count('id', filter=Q(llm_ok=False)),
                trades_executed=Sum('trades_executed'),
            )

            recent_runs = [
                self._serialize_run(run)
                for run in recent_qs[:20]
            ]
        except Exception as e:
            logger.warning(f"AgentStatusView.get migration/DB issue: {e}")
            return Response({
                'status': 'unavailable',
                'reason': 'agent_run_logs table is not ready',
                'last_run': None,
                'last_trade_run': None,
                'last_llm_issue': None,
                'last_24h': {
                    'runs': 0,
                    'success_runs': 0,
                    'no_trade_runs': 0,
                    'skipped_runs': 0,
                    'error_runs': 0,
                    'no_response_runs': 0,
                    'llm_failures': 0,
                    'trades_executed': 0,
                },
                'recent_runs': [],
            })

        elapsed = time.time() - start_time
        logger.info(f"AgentStatusView.get completed in {elapsed:.2f}s")

        return Response({
            'last_run': self._serialize_run(last_run),
            'last_trade_run': self._serialize_run(last_trade_run),
            'last_llm_issue': self._serialize_run(last_llm_issue),
            'last_24h': {
                'runs': stats_24h.get('runs') or 0,
                'success_runs': stats_24h.get('success_runs') or 0,
                'no_trade_runs': stats_24h.get('no_trade_runs') or 0,
                'skipped_runs': stats_24h.get('skipped_runs') or 0,
                'error_runs': stats_24h.get('error_runs') or 0,
                'no_response_runs': stats_24h.get('no_response_runs') or 0,
                'llm_failures': stats_24h.get('llm_failures') or 0,
                'trades_executed': stats_24h.get('trades_executed') or 0,
            },
            'recent_runs': recent_runs,
        })


class OperationsSummaryView(APIView):
    """Operational health summary for monitoring app behavior."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_time = time.time()
        logger.info("OperationsSummaryView.get called")
        days = request.query_params.get('days', 14)
        try:
            summary = build_operations_summary(days=days)
            elapsed = time.time() - start_time
            logger.info(f"OperationsSummaryView.get completed in {elapsed:.2f}s")
            return Response(summary)
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"OperationsSummaryView.get failed in {elapsed:.2f}s: {e}")
            return Response({'error': str(e)}, status=500)


class AnalyzeLogsView(APIView):
    """Detailed analyze-run logs for diagnostics and export."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def _is_truthy(value):
        return str(value).strip().lower() in ('1', 'true', 'yes', 'on')

    @staticmethod
    def _serialize_run(run, include_details=False):
        issue_type = classify_operational_issue(run.message, run.llm_error)
        payload = {
            'id': run.id,
            'time': timezone.localtime(run.created_at).isoformat(),
            'status': run.status,
            'message': run.message or '',
            'duration_ms': run.duration_ms,
            'market_open': run.market_open,
            'llm_ok': run.llm_ok,
            'llm_error': run.llm_error or '',
            'trades_recommended': run.trades_recommended or 0,
            'trades_executed': run.trades_executed or 0,
            'issue_type': issue_type,
            'symbol': run.symbol or '',
            'option_type': run.option_type or '',
            'strike': float(run.strike) if run.strike is not None else None,
        }
        if include_details:
            payload['details'] = run.details or {}
        return payload

    def get(self, request):
        start_time = time.time()
        logger.info("AnalyzeLogsView.get called")
        try:
            from trading_api.models.trade import AgentRunLog

            days = int(request.query_params.get('days', 14) or 14)
            days = max(1, min(days, 365))

            limit = int(request.query_params.get('limit', 200) or 200)
            limit = max(1, min(limit, 2000))

            include_details = self._is_truthy(request.query_params.get('include_details', '0'))
            # Do not use query param "format" here; DRF reserves it for renderer negotiation.
            export_format = (
                request.query_params.get('export')
                or request.query_params.get('download')
                or 'json'
            ).strip().lower()

            valid_statuses = {choice[0] for choice in AgentRunLog.STATUS_CHOICES}
            requested_statuses = [
                s.strip().lower()
                for s in str(request.query_params.get('status', '')).split(',')
                if s.strip()
            ]
            selected_statuses = [s for s in requested_statuses if s in valid_statuses]

            since = timezone.now() - timedelta(days=days)
            queryset = AgentRunLog.objects.filter(
                run_type='analyze',
                created_at__gte=since
            ).order_by('-created_at')

            if selected_statuses:
                queryset = queryset.filter(status__in=selected_statuses)

            total = queryset.count()
            runs = list(queryset[:limit])
            rows = [self._serialize_run(run, include_details=include_details) for run in runs]

            if export_format == 'csv':
                stamp = timezone.localtime().strftime('%Y%m%d_%H%M%S')
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = f'attachment; filename="analyze_logs_{stamp}.csv"'
                writer = csv.writer(response)
                writer.writerow([
                    'time',
                    'status',
                    'duration_ms',
                    'market_open',
                    'llm_ok',
                    'trades_recommended',
                    'trades_executed',
                    'issue_type',
                    'symbol',
                    'option_type',
                    'strike',
                    'message',
                    'llm_error',
                ])
                for row in rows:
                    writer.writerow([
                        row.get('time') or '',
                        row.get('status') or '',
                        row.get('duration_ms') if row.get('duration_ms') is not None else '',
                        row.get('market_open') if row.get('market_open') is not None else '',
                        row.get('llm_ok') if row.get('llm_ok') is not None else '',
                        row.get('trades_recommended', 0),
                        row.get('trades_executed', 0),
                        row.get('issue_type') or '',
                        row.get('symbol') or '',
                        row.get('option_type') or '',
                        row.get('strike') if row.get('strike') is not None else '',
                        row.get('message') or '',
                        row.get('llm_error') or '',
                    ])
                elapsed = time.time() - start_time
                logger.info(
                    f"AnalyzeLogsView.get CSV completed in {elapsed:.2f}s: "
                    f"{len(rows)}/{total} rows"
                )
                return response

            elapsed = time.time() - start_time
            logger.info(
                f"AnalyzeLogsView.get completed in {elapsed:.2f}s: "
                f"{len(rows)}/{total} rows"
            )
            return Response({
                'days': days,
                'limit': limit,
                'total': total,
                'returned': len(rows),
                'status_filter': selected_statuses,
                'logs': rows,
            })

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"AnalyzeLogsView.get failed in {elapsed:.2f}s: {e}")
            return Response({'error': str(e)}, status=500)


class PlaidLinkTokenView(APIView):
    """Create Plaid Link token for client-side Link flow."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from trading_api.services.plaid_service import PlaidClient, PlaidServiceError

        mode = (request.data.get('mode') or 'investments').strip().lower()
        client = PlaidClient()
        if not client.is_configured:
            return Response({
                'error': 'Plaid credentials are not configured on the backend.',
            }, status=500)

        try:
            payload = client.create_link_token(user_id=str(request.user.id), mode=mode)
            return Response({
                'link_token': payload.get('link_token'),
                'expiration': payload.get('expiration'),
                'request_id': payload.get('request_id'),
                'mode': mode,
                'env': client.env,
            })
        except PlaidServiceError as exc:
            return Response({
                'error': exc.info.message,
                'error_code': exc.info.error_code,
                'error_type': exc.info.error_type,
                'request_id': exc.info.request_id,
            }, status=400)


class PlaidExchangeTokenView(APIView):
    """Exchange Plaid public token, persist item, and perform initial sync."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from trading_api.models import PlaidItem
        from trading_api.services.plaid_service import PlaidClient, PlaidServiceError, sync_item_data

        public_token = (request.data.get('public_token') or '').strip()
        mode = (request.data.get('mode') or 'investments').strip().lower()
        if not public_token:
            return Response({'error': 'public_token is required.'}, status=400)
        if mode not in {'investments', 'bank'}:
            mode = 'investments'

        client = PlaidClient()
        try:
            exchange = client.exchange_public_token(public_token)
            access_token = exchange.get('access_token')
            item_id = exchange.get('item_id')
            if not access_token or not item_id:
                return Response({'error': 'Plaid exchange response missing item token.'}, status=502)

            item_payload = client.get_item(access_token).get('item') or {}
            institution_id = item_payload.get('institution_id') or ''
            institution_name = client.get_institution_name(institution_id) if institution_id else ''
            consent_exp = item_payload.get('consent_expiration_time')
            consent_exp_dt = None
            if consent_exp:
                try:
                    consent_exp_dt = timezone.datetime.fromisoformat(str(consent_exp).replace('Z', '+00:00'))
                except Exception:
                    consent_exp_dt = None

            existing = PlaidItem.objects.filter(item_id=item_id).first()
            if existing and existing.user_id != request.user.id:
                return Response({
                    'error': 'This Plaid item is already linked to another user.',
                }, status=409)

            plaid_item, _ = PlaidItem.objects.update_or_create(
                item_id=item_id,
                defaults={
                    'user': request.user,
                    'access_token': access_token,
                    'institution_id': institution_id,
                    'institution_name': institution_name,
                    'product_type': mode,
                    'status': 'active',
                    'last_error': '',
                    'consent_expiration_time': consent_exp_dt,
                },
            )

            sync_result = sync_item_data(plaid_item, triggered_by=request.user)

            return Response({
                'success': True,
                'item': {
                    'id': plaid_item.id,
                    'item_id': plaid_item.item_id,
                    'institution_name': plaid_item.institution_name,
                    'product_type': plaid_item.product_type,
                    'status': plaid_item.status,
                    'last_sync_at': timezone.localtime(plaid_item.last_sync_at).isoformat()
                    if plaid_item.last_sync_at else None,
                },
                'sync': sync_result,
            })

        except PlaidServiceError as exc:
            return Response({
                'error': exc.info.message,
                'error_code': exc.info.error_code,
                'error_type': exc.info.error_type,
                'request_id': exc.info.request_id,
            }, status=400)
        except Exception as exc:
            logger.exception('Plaid token exchange failed')
            return Response({'error': str(exc)}, status=500)


class PlaidOverviewView(APIView):
    """Return connected Plaid items with accounts/holdings/transactions."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def _serialize_account(account):
        return {
            'id': account.id,
            'account_id': account.account_id,
            'name': account.name,
            'official_name': account.official_name,
            'mask': account.mask,
            'type': account.account_type,
            'subtype': account.subtype,
            'current_balance': float(account.current_balance) if account.current_balance is not None else None,
            'available_balance': float(account.available_balance) if account.available_balance is not None else None,
            'currency': account.iso_currency_code or account.unofficial_currency_code or 'USD',
            'last_sync_at': timezone.localtime(account.last_sync_at).isoformat()
            if account.last_sync_at else None,
        }

    @staticmethod
    def _serialize_item(item):
        accounts = [PlaidOverviewView._serialize_account(acc) for acc in item.accounts.all().order_by('name')]
        return {
            'id': item.id,
            'item_id': item.item_id,
            'institution_name': item.institution_name or item.institution_id or item.item_id,
            'institution_id': item.institution_id,
            'product_type': item.product_type,
            'status': item.status,
            'last_error': item.last_error,
            'last_sync_at': timezone.localtime(item.last_sync_at).isoformat() if item.last_sync_at else None,
            'last_success_at': timezone.localtime(item.last_success_at).isoformat() if item.last_success_at else None,
            'accounts': accounts,
            'counts': {
                'accounts': len(accounts),
                'holdings': item.holdings.count(),
                'transactions': item.investment_transactions.count(),
            },
        }

    def get(self, request):
        from trading_api.models import PlaidHolding, PlaidInvestmentTransaction, PlaidItem, PlaidSyncLog
        from trading_api.services.plaid_service import PlaidClient

        limit_holdings = max(1, min(int(request.query_params.get('holdings_limit', 200) or 200), 1000))
        limit_transactions = max(1, min(int(request.query_params.get('transactions_limit', 200) or 200), 1000))
        limit_logs = max(1, min(int(request.query_params.get('logs_limit', 50) or 50), 200))

        items_qs = PlaidItem.objects.filter(user=request.user).prefetch_related('accounts', 'holdings', 'investment_transactions')
        items = [self._serialize_item(item) for item in items_qs]

        holdings_qs = PlaidHolding.objects.filter(item__user=request.user).select_related(
            'item', 'account', 'security'
        ).order_by('-institution_value', '-updated_at')[:limit_holdings]
        holdings_list = list(holdings_qs)
        metric_symbol_by_holding_id = {}
        metric_symbols = []
        for holding in holdings_list:
            sec = holding.security
            lookup_symbol = _resolve_metric_symbol(
                symbol=(sec.ticker_symbol if sec else '') or '',
                security_type=(sec.security_type if sec else '') or '',
                security_name=(sec.name if sec else '') or '',
            )
            metric_symbol_by_holding_id[holding.id] = lookup_symbol
            if lookup_symbol:
                metric_symbols.append(lookup_symbol)
        metrics_by_symbol = _get_position_market_metrics(metric_symbols)

        holdings = []
        for h in holdings_list:
            security = h.security
            quantity = float(h.quantity) if h.quantity is not None else None
            price = float(h.institution_price) if h.institution_price is not None else None
            value = float(h.institution_value) if h.institution_value is not None else None
            cost_basis = float(h.cost_basis) if h.cost_basis is not None else None

            cost_basis_per_share = None
            if quantity and quantity != 0 and cost_basis is not None:
                cost_basis_per_share = cost_basis / quantity

            total_gain_pct = None
            if cost_basis and cost_basis != 0 and value is not None:
                total_gain_pct = ((value - cost_basis) / cost_basis) * 100.0
            total_gain_value = (value - cost_basis) if (value is not None and cost_basis is not None) else None

            metric_symbol = metric_symbol_by_holding_id.get(h.id) or ''
            symbol_metrics = metrics_by_symbol.get(metric_symbol, {})
            option_type = _infer_option_type(
                symbol=(security.ticker_symbol if security else '') or '',
                security_type=(security.security_type if security else '') or '',
                security_name=(security.name if security else '') or '',
                security_raw=(security.raw if security else None),
            )

            holdings.append({
                'id': h.id,
                'institution_name': h.item.institution_name or h.item.institution_id or h.item.item_id,
                'account_name': h.account.name or h.account.account_id,
                'symbol': (security.ticker_symbol if security else '') or '',
                'security_name': (security.name if security else '') or '',
                'security_type': (security.security_type if security else '') or '',
                'option_type': option_type or '',
                'metric_symbol': metric_symbol,
                'quantity': quantity,
                'price': price,
                'value': value,
                'cost_basis': cost_basis,
                'cost_basis_per_share': cost_basis_per_share,
                'total_gain_pct': total_gain_pct,
                'total_gain_value': total_gain_value,
                'change_pct': symbol_metrics.get('day_change_pct'),
                'forward_pe': symbol_metrics.get('forward_pe'),
                'volatility_pct': symbol_metrics.get('volatility_pct'),
                'week_52_high': symbol_metrics.get('week_52_high'),
                'week_52_low': symbol_metrics.get('week_52_low'),
                'ytd_gain_pct': symbol_metrics.get('ytd_return_pct'),
                'currency': h.iso_currency_code or h.unofficial_currency_code or 'USD',
                'updated_at': timezone.localtime(h.updated_at).isoformat(),
            })

        transactions_qs = PlaidInvestmentTransaction.objects.filter(item__user=request.user).select_related(
            'item', 'account', 'security'
        ).order_by('-date', '-updated_at')[:limit_transactions]
        transactions = [{
            'id': tx.id,
            'institution_name': tx.item.institution_name or tx.item.institution_id or tx.item.item_id,
            'date': tx.date.isoformat() if tx.date else None,
            'name': tx.name,
            'symbol': tx.ticker_symbol or (tx.security.ticker_symbol if tx.security else ''),
            'type': tx.tx_type,
            'subtype': tx.subtype,
            'quantity': float(tx.quantity) if tx.quantity is not None else None,
            'price': float(tx.price) if tx.price is not None else None,
            'amount': float(tx.amount) if tx.amount is not None else None,
            'fees': float(tx.fees) if tx.fees is not None else None,
            'currency': tx.iso_currency_code or tx.unofficial_currency_code or 'USD',
            'account_name': tx.account.name if tx.account else '',
            'updated_at': timezone.localtime(tx.updated_at).isoformat(),
        } for tx in transactions_qs]

        logs_qs = PlaidSyncLog.objects.filter(item__user=request.user).select_related('item').order_by('-started_at')[:limit_logs]
        sync_logs = [{
            'id': log.id,
            'institution_name': log.item.institution_name if log.item else '',
            'status': log.status,
            'message': log.message,
            'accounts_synced': log.accounts_synced,
            'holdings_synced': log.holdings_synced,
            'transactions_synced': log.transactions_synced,
            'started_at': timezone.localtime(log.started_at).isoformat() if log.started_at else None,
            'ended_at': timezone.localtime(log.ended_at).isoformat() if log.ended_at else None,
            'duration_ms': log.duration_ms,
            'details': log.details or {},
        } for log in logs_qs]

        client = PlaidClient()
        return Response({
            'configured': client.is_configured,
            'env': client.env,
            'manual_sync_only': True,
            'items': items,
            'holdings': holdings,
            'transactions': transactions,
            'sync_logs': sync_logs,
        })


class PlaidItemSyncView(APIView):
    """Trigger manual sync for one Plaid item."""

    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        from trading_api.models import PlaidItem
        from trading_api.services.plaid_service import PlaidServiceError, sync_item_data

        try:
            item = PlaidItem.objects.get(id=item_id, user=request.user)
        except PlaidItem.DoesNotExist:
            return Response({'error': 'Plaid item not found.'}, status=404)

        try:
            result = sync_item_data(item, triggered_by=request.user)
            return Response({
                'success': True,
                'item_id': item.id,
                'result': result,
            })
        except PlaidServiceError as exc:
            return Response({
                'error': exc.info.message,
                'error_code': exc.info.error_code,
                'error_type': exc.info.error_type,
            }, status=400)
        except Exception as exc:
            logger.exception('Plaid manual sync failed')
            return Response({'error': str(exc)}, status=500)


class PlaidItemDisconnectView(APIView):
    """Disconnect Plaid item and delete cached data."""

    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        from trading_api.models import PlaidItem
        from trading_api.services.plaid_service import PlaidClient

        try:
            item = PlaidItem.objects.get(id=item_id, user=request.user)
        except PlaidItem.DoesNotExist:
            return Response({'error': 'Plaid item not found.'}, status=404)

        client = PlaidClient()
        if client.is_configured:
            try:
                client.remove_item(item.access_token)
            except Exception as exc:
                logger.warning(f'Plaid item remove call failed for {item.item_id}: {exc}')

        item.delete()
        return Response({'success': True})


class ConfigView(APIView):
    """Get trading configuration."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def _test_ibkr_connection():
        import socket
        import os

        host = os.environ.get('IBKR_GATEWAY_HOST', '10.138.0.3')
        port = int(os.environ.get('IBKR_GATEWAY_PORT', '4002'))

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            result = sock.connect_ex((host, port))
            api_conn = "success" if result == 0 else f"failed (code={result})"
        except Exception as e:
            api_conn = f"error: {str(e)}"
        finally:
            sock.close()

        return host, port, api_conn

    @staticmethod
    def _build_response_payload(effective_settings, host, port, api_conn):
        import os

        trading_config = settings.TRADING_CONFIG
        broker_type_env = os.environ.get('BROKER_TYPE', 'unknown')
        broker_name = get_broker_info()

        return {
            'broker': broker_name,
            'debug_broker_type_env': broker_type_env,
            'debug_broker_name_computed': broker_name,
            'ibkr_connection_test': api_conn,
            'ibkr_host': host,
            'ibkr_port': port,
            'watchlist': trading_config['WATCHLIST'],
            'analysis_interval': effective_settings['analysis_interval'],
            'max_position_pct': effective_settings['max_position_pct'],
            'max_daily_loss_pct': effective_settings['max_daily_loss_pct'],
            'min_confidence': effective_settings['min_confidence'],
            'stop_loss_pct': effective_settings['stop_loss_pct'],
            'take_profit_pct': effective_settings['take_profit_pct'],
            'indicator_settings': _normalize_indicator_settings(
                effective_settings.get('indicator_settings')
            ),
            'available_indicators': [
                {'key': key, 'label': label}
                for key, label in INDICATOR_LABELS.items()
            ],
            'initial_capital': float(
                os.environ.get(
                    'INITIAL_CAPITAL',
                    trading_config.get('INITIAL_CAPITAL', 1000000)
                )
            ),
        }

    def get(self, request):
        start_time = time.time()
        logger.info("ConfigView.get called")

        effective_settings = apply_runtime_trading_settings()
        host, port, api_conn = self._test_ibkr_connection()
        payload = self._build_response_payload(effective_settings, host, port, api_conn)

        elapsed = time.time() - start_time
        logger.info(
            f"ConfigView.get completed in {elapsed:.2f}s: "
            f"broker={payload['broker']}, tcp={api_conn}"
        )
        return Response(payload)

    def post(self, request):
        start_time = time.time()
        logger.info("ConfigView.post called")

        data = request.data or {}
        errors = {}
        updates = {}

        def parse_pct(field, min_value=0, max_value=100):
            if field not in data:
                return
            try:
                value = float(data.get(field))
                if value < min_value or value > max_value:
                    errors[field] = f"Must be between {min_value} and {max_value}"
                else:
                    updates[field] = value
            except (TypeError, ValueError):
                errors[field] = "Must be a number"

        if 'analysis_interval' in data:
            try:
                interval = int(data.get('analysis_interval'))
                if interval < 1 or interval > 1440:
                    errors['analysis_interval'] = "Must be between 1 and 1440 minutes"
                else:
                    updates['analysis_interval'] = interval
            except (TypeError, ValueError):
                errors['analysis_interval'] = "Must be an integer"

        parse_pct('max_position_pct', 0.1, 100)
        parse_pct('max_daily_loss_pct', 0.1, 100)
        parse_pct('min_confidence', 0, 100)
        parse_pct('stop_loss_pct', 0.1, 100)
        parse_pct('take_profit_pct', 0.1, 500)

        if 'indicator_settings' in data:
            if not isinstance(data.get('indicator_settings'), dict):
                errors['indicator_settings'] = "Must be a key/value object"
            else:
                updates['indicator_settings'] = _normalize_indicator_settings(
                    data.get('indicator_settings')
                )

        if errors:
            return Response({'success': False, 'errors': errors}, status=400)

        if not updates:
            return Response({'success': False, 'error': 'No fields provided to update'}, status=400)

        from trading_api.models import AgentSettings
        from django.db.utils import OperationalError, ProgrammingError

        try:
            settings_obj, _ = AgentSettings.objects.get_or_create(singleton_key='default')
        except (ProgrammingError, OperationalError) as exc:
            # Self-heal path: if schema migration did not apply yet, attempt
            # to run trading_api migrations and retry once.
            err = str(exc).lower()
            missing_table = (
                'agent_settings' in err and (
                    'does not exist' in err
                    or 'undefined table' in err
                    or 'no such table' in err
                )
            )
            if not missing_table:
                raise

            logger.warning("AgentSettings table missing; attempting migration before retry")
            try:
                from django.core.management import call_command
                call_command('migrate', 'trading_api', interactive=False, verbosity=0)
                settings_obj, _ = AgentSettings.objects.get_or_create(singleton_key='default')
            except Exception as migration_exc:
                logger.error(f"ConfigView.post migration self-heal failed: {migration_exc}")
                return Response(
                    {
                        'success': False,
                        'error': (
                            'Settings storage is not ready yet. '
                            'Please retry in a minute after migrations complete.'
                        ),
                    },
                    status=503,
                )

        if 'analysis_interval' in updates:
            settings_obj.analysis_interval_minutes = updates['analysis_interval']
        if 'max_position_pct' in updates:
            settings_obj.max_position_pct = updates['max_position_pct'] / 100.0
        if 'max_daily_loss_pct' in updates:
            settings_obj.max_daily_loss_pct = updates['max_daily_loss_pct'] / 100.0
        if 'min_confidence' in updates:
            settings_obj.min_confidence = updates['min_confidence'] / 100.0
        if 'stop_loss_pct' in updates:
            settings_obj.stop_loss_pct = updates['stop_loss_pct'] / 100.0
        if 'take_profit_pct' in updates:
            settings_obj.take_profit_pct = updates['take_profit_pct'] / 100.0
        if 'indicator_settings' in updates:
            settings_obj.indicator_settings = updates['indicator_settings']

        settings_obj.save()
        effective_settings = apply_runtime_trading_settings()
        host, port, api_conn = self._test_ibkr_connection()
        payload = self._build_response_payload(effective_settings, host, port, api_conn)
        payload['success'] = True
        payload['message'] = "Settings updated"

        elapsed = time.time() - start_time
        logger.info(f"ConfigView.post completed in {elapsed:.2f}s")
        return Response(payload)


class IndicatorsView(APIView):
    """Get technical indicators for watchlist symbols."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_time = time.time()
        logger.info("IndicatorsView.get called")
        try:
            effective_settings = apply_runtime_trading_settings()
            enabled_indicators = _normalize_indicator_settings(
                effective_settings.get('indicator_settings')
            )
            import math
            import pandas as pd
            import yfinance as yf
            from trading_api.services import get_technical_indicators
            TechnicalIndicators = get_technical_indicators()

            top_symbols = tuple(settings.TRADING_CONFIG['WATCHLIST'][:10])

            # Cache check
            now = time.time()
            with _indicators_cache_lock:
                cache_hit = (
                    _indicators_cache['results']
                    and _indicators_cache['symbols'] == top_symbols
                    and (now - _indicators_cache['timestamp']) < _INDICATORS_CACHE_TTL_SECONDS
                )
                if cache_hit:
                    logger.info("IndicatorsView.get served from cache")
                    return Response({'indicators': _indicators_cache['results']})

            # Batch download for all symbols to avoid per-symbol rate limits
            downloaded = yf.download(
                tickers=' '.join(top_symbols),
                period='3mo',
                interval='1d',
                group_by='ticker',
                auto_adjust=False,
                progress=False,
                threads=False,
            )

            def _extract_symbol_df(symbol):
                if downloaded is None or getattr(downloaded, 'empty', True):
                    return None
                if isinstance(downloaded.columns, pd.MultiIndex):
                    if symbol not in downloaded.columns.get_level_values(0):
                        return None
                    df = downloaded[symbol].copy()
                else:
                    # Single-symbol download format
                    if len(top_symbols) != 1 or symbol != top_symbols[0]:
                        return None
                    df = downloaded.copy()
                df = df.dropna(how='all')
                return df if not df.empty else None

            def _safe_float(value):
                try:
                    f = float(value)
                    if math.isnan(f) or math.isinf(f):
                        return None
                    return f
                except (TypeError, ValueError):
                    return None

            results = []
            for symbol in top_symbols:
                try:
                    df = _extract_symbol_df(symbol)
                    if df is None or len(df) < 30:
                        results.append({
                            'symbol': symbol,
                            'price': 0,
                            'rsi': None,
                            'rsi_signal': 'NO DATA',
                            'macd': None,
                            'macd_trend': 'NO DATA',
                            'overall_signal': 'NO DATA'
                        })
                        continue

                    tech_data = TechnicalIndicators(df).calculate_all(enabled_indicators)
                    close_series = df['Close'] if 'Close' in df.columns else df.iloc[:, 0]
                    current_price = _safe_float(close_series.ffill().iloc[-1]) or 0

                    rsi = _safe_float(tech_data.get('rsi'))
                    macd = _safe_float(tech_data.get('macd'))
                    macd_trend = str(tech_data.get('macd_signal') or 'NEUTRAL').upper()

                    if not enabled_indicators.get('rsi', True):
                        rsi_signal = 'DISABLED'
                    elif rsi is None:
                        rsi_signal = 'NO DATA'
                    elif rsi > 70:
                        rsi_signal = 'OVERBOUGHT'
                    elif rsi < 30:
                        rsi_signal = 'OVERSOLD'
                    elif rsi >= 60:
                        rsi_signal = 'BULLISH'
                    elif rsi <= 40:
                        rsi_signal = 'BEARISH'
                    else:
                        rsi_signal = 'NEUTRAL'

                    if not enabled_indicators.get('macd', True):
                        macd_trend = 'DISABLED'

                    overall = 'NEUTRAL'
                    bullish_votes = 0
                    bearish_votes = 0
                    if rsi_signal in ('OVERSOLD', 'BULLISH'):
                        bullish_votes += 1
                    elif rsi_signal in ('OVERBOUGHT', 'BEARISH'):
                        bearish_votes += 1
                    if macd_trend == 'BULLISH':
                        bullish_votes += 1
                    elif macd_trend == 'BEARISH':
                        bearish_votes += 1
                    if bullish_votes > bearish_votes:
                        overall = 'BULLISH'
                    elif bearish_votes > bullish_votes:
                        overall = 'BEARISH'

                    results.append({
                        'symbol': symbol,
                        'price': round(current_price, 2),
                        'rsi': round(rsi, 2) if rsi is not None else None,
                        'rsi_signal': rsi_signal,
                        'macd': round(macd, 4) if macd is not None else None,
                        'macd_trend': macd_trend,
                        'overall_signal': overall
                    })
                except Exception as e:
                    logger.error(f"Indicator error for {symbol}: {e}")
                    results.append({
                        'symbol': symbol,
                        'price': 0,
                        'rsi': None,
                        'rsi_signal': 'ERROR',
                        'macd': None,
                        'macd_trend': 'ERROR',
                        'overall_signal': 'ERROR'
                    })

            with _indicators_cache_lock:
                _indicators_cache['timestamp'] = time.time()
                _indicators_cache['symbols'] = top_symbols
                _indicators_cache['results'] = results

            elapsed = time.time() - start_time
            logger.info(
                f"IndicatorsView.get completed in {elapsed:.2f}s: "
                f"{len(results)} indicators"
            )
            return Response({'indicators': results})

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"IndicatorsView.get failed in {elapsed:.2f}s: {e}")
            return Response({'error': str(e), 'indicators': []}, status=500)


class OptionChainView(APIView):
    """Get option chain data for a symbol at a specific strike across all expirations."""

    permission_classes = [AllowAny]  # Public endpoint using free yfinance data

    @staticmethod
    def _extract_strike_row(df, strike):
        """Return closest row for requested strike."""
        if df is None or df.empty:
            return None, None
        strike_match = df[df['strike'] == strike]
        if strike_match.empty:
            closest_idx = (df['strike'] - strike).abs().idxmin()
            strike_match = df.loc[[closest_idx]]
        actual_strike = float(strike_match['strike'].iloc[0])
        return actual_strike, strike_match.iloc[0]

    @staticmethod
    def _mid_price(row):
        bid = float(row.get('bid', 0) or 0)
        ask = float(row.get('ask', 0) or 0)
        last = float(row.get('lastPrice', 0) or 0)
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        return last

    @staticmethod
    def _attach_nearest_candidate(recommendation, candidates):
        """Attach liquidity/timing fields using best matching candidate contract.

        Ensures expiration and DTE stay consistent in UI by preferring
        exact expiration matches when present.
        """
        same_type = [
            c for c in candidates
            if c['option_type'] == recommendation.get('option_type')
        ]
        if not same_type:
            return recommendation

        rec_exp = str(recommendation.get('expiration') or '').strip()
        rec_strike = float(recommendation.get('strike', 0) or 0)
        rec_days = recommendation.get('days_to_expiry')
        if rec_days is None:
            rec_days = 30
        else:
            rec_days = int(rec_days)

        nearest = min(
            same_type,
            key=lambda c: (
                0 if (rec_exp and c.get('expiration') == rec_exp) else 1,
                abs(float(c.get('strike') or 0) - rec_strike),
                abs(int(c.get('days_to_expiry') or 0) - rec_days),
            )
        )

        # If no exact-expiration candidate was found, sync recommendation
        # identity to the attached contract to avoid expiration/DTE mismatch.
        if rec_exp and nearest.get('expiration') != rec_exp:
            recommendation.update({
                'expiration': nearest.get('expiration'),
                'strike': nearest.get('strike'),
                'premium': nearest.get('premium', recommendation.get('premium')),
            })

        recommendation.update({
            'open_interest': nearest.get('open_interest', 0),
            'volume': nearest.get('volume', 0),
            'days_to_expiry': nearest.get('days_to_expiry'),
            'implied_volatility_pct': nearest.get('implied_volatility_pct'),
        })
        return recommendation

    @staticmethod
    def _heuristic_sell_recommendation(symbol, current_price, candidates):
        """Fallback recommendation when LLM is unavailable.

        Prefers liquid contracts with reasonable DTE and moderate delta.
        """
        if not candidates:
            return None

        def _score(c):
            days = c.get('days_to_expiry', 0)
            oi = float(c.get('open_interest', 0) or 0)
            vol = float(c.get('volume', 0) or 0)
            premium = float(c.get('premium', 0) or 0)
            delta = c.get('delta')

            liquidity_score = min(oi / 2500.0, 1.0) * 0.35 + min(vol / 1200.0, 1.0) * 0.25
            premium_score = min(premium / 5.0, 1.0) * 0.20
            dte_score = max(0.0, 1.0 - (abs(days - 30) / 30.0)) * 0.10

            delta_score = 0.05
            if delta is not None:
                target = 0.25 if c.get('option_type') == 'CALL' else -0.25
                delta_score = max(0.0, 1.0 - abs(float(delta) - target) / 0.4) * 0.10

            return liquidity_score + premium_score + dte_score + delta_score

        ranked = sorted(candidates, key=_score, reverse=True)
        best = ranked[0]
        best_score = _score(best)

        recommendation = {
            'option_type': best.get('option_type'),
            'expiration': best.get('expiration'),
            'strike': float(best.get('strike') or 0),
            'premium': float(best.get('premium') or 0),
            'confidence': round(min(0.50 + (best_score * 0.4), 0.88), 2),
            'reasoning': (
                f"Heuristic fallback for {symbol}: selected {best.get('option_type')} "
                f"{best.get('strike')} {best.get('expiration')} based on liquidity "
                f"(OI {int(best.get('open_interest') or 0)}, Vol {int(best.get('volume') or 0)}), "
                f"premium ${float(best.get('premium') or 0):.2f}, and DTE {best.get('days_to_expiry')}."
            ),
            'generated_by': 'heuristic'
        }
        return recommendation

    def get(self, request):
        start_time = time.time()

        symbol = request.GET.get('symbol', '').upper()
        strike_str = request.GET.get('strike')
        option_type = request.GET.get('type', 'call').lower()
        with_recommendation = str(
            request.GET.get('with_recommendation', 'false')
        ).lower() in ('1', 'true', 'yes')

        if not symbol:
            return Response({'error': 'symbol parameter is required'}, status=400)
        if not strike_str:
            return Response({'error': 'strike parameter is required'}, status=400)
        if option_type not in ('call', 'put'):
            return Response({'error': 'type must be "call" or "put"'}, status=400)

        try:
            strike = float(strike_str)
        except ValueError:
            return Response({'error': 'strike must be a valid number'}, status=400)

        logger.info(f"OptionChainView.get: {symbol} ${strike} {option_type}")

        try:
            import yfinance as yf
            from datetime import datetime as dt
            from src.utils.greeks import black_scholes_greeks

            ticker = yf.Ticker(symbol)

            # Current stock price
            current_price = None
            try:
                info = ticker.info
                current_price = info.get('regularMarketPrice') or info.get('currentPrice')
                if not current_price:
                    hist = ticker.history(period='1d')
                    current_price = float(hist['Close'].iloc[-1]) if len(hist) > 0 else None
            except Exception as e:
                logger.warning(f"OptionChainView: could not get price for {symbol}: {e}")

            # All expiration dates
            try:
                expirations = ticker.options
            except Exception:
                return Response(
                    {'error': f'No options data available for {symbol}'},
                    status=404,
                )

            if not expirations:
                return Response(
                    {'error': f'No option expirations found for {symbol}'},
                    status=404,
                )

            logger.info(f"OptionChainView: {len(expirations)} expirations for {symbol}")

            risk_free_rate = 0.045  # ~4.5 % US Treasury approximation
            options_data = []
            sell_candidates = []

            for exp_date in expirations:
                try:
                    chain = ticker.option_chain(exp_date)
                    display_df = chain.calls if option_type == 'call' else chain.puts

                    # Find exact or closest strike
                    actual_strike, row = self._extract_strike_row(display_df, strike)
                    if row is None:
                        continue
                    last_price = float(row.get('lastPrice', 0) or 0)
                    bid = float(row.get('bid', 0) or 0)
                    ask = float(row.get('ask', 0) or 0)
                    volume = int(row.get('volume', 0) or 0)
                    open_interest = int(row.get('openInterest', 0) or 0)
                    implied_vol = float(row.get('impliedVolatility', 0) or 0)

                    exp_datetime = dt.strptime(exp_date, '%Y-%m-%d')
                    days_to_expiry = (exp_datetime - dt.now()).days
                    time_to_expiry = max(days_to_expiry, 0) / 365.0

                    # Greeks via Black-Scholes
                    greeks = {'delta': None, 'gamma': None, 'theta': None, 'vega': None}
                    if current_price and implied_vol > 0 and time_to_expiry > 0:
                        greeks = black_scholes_greeks(
                            option_type=option_type,
                            stock_price=current_price,
                            strike_price=actual_strike,
                            time_to_expiry=time_to_expiry,
                            risk_free_rate=risk_free_rate,
                            implied_volatility=implied_vol,
                        )

                    options_data.append({
                        'expiration': exp_date,
                        'days_to_expiry': days_to_expiry,
                        'strike': actual_strike,
                        'last_price': last_price,
                        'bid': bid,
                        'ask': ask,
                        'volume': volume,
                        'open_interest': open_interest,
                        'implied_volatility': round(implied_vol * 100, 2),
                        'delta': greeks.get('delta'),
                        'gamma': greeks.get('gamma'),
                        'theta': greeks.get('theta'),
                        'vega': greeks.get('vega'),
                    })

                    # Build recommendation candidates for BOTH calls and puts.
                    for sell_type, sell_df in (('CALL', chain.calls), ('PUT', chain.puts)):
                        rec_strike, rec_row = self._extract_strike_row(sell_df, strike)
                        if rec_row is None:
                            continue
                        premium = self._mid_price(rec_row)
                        if premium <= 0:
                            continue
                        rec_bid = float(rec_row.get('bid', 0) or 0)
                        rec_ask = float(rec_row.get('ask', 0) or 0)
                        rec_volume = int(rec_row.get('volume', 0) or 0)
                        rec_oi = int(rec_row.get('openInterest', 0) or 0)
                        rec_iv = float(rec_row.get('impliedVolatility', 0) or 0)

                        rec_greeks = {'delta': None, 'theta': None}
                        if current_price and rec_iv > 0 and time_to_expiry > 0:
                            rec_greeks = black_scholes_greeks(
                                option_type=sell_type.lower(),
                                stock_price=current_price,
                                strike_price=rec_strike,
                                time_to_expiry=time_to_expiry,
                                risk_free_rate=risk_free_rate,
                                implied_volatility=rec_iv,
                            )

                        sell_candidates.append({
                            'option_type': sell_type,
                            'expiration': exp_date,
                            'days_to_expiry': days_to_expiry,
                            'strike': rec_strike,
                            'premium': round(float(premium), 4),
                            'bid': rec_bid,
                            'ask': rec_ask,
                            'volume': rec_volume,
                            'open_interest': rec_oi,
                            'implied_volatility_pct': round(rec_iv * 100, 2),
                            'delta': rec_greeks.get('delta'),
                            'theta': rec_greeks.get('theta'),
                        })
                except Exception as e:
                    logger.warning(f"OptionChainView: error for {exp_date}: {e}")
                    continue

            options_data.sort(key=lambda x: x['expiration'])

            recommendation = None
            recommendation_error = None
            if with_recommendation and current_price and sell_candidates:
                try:
                    from trading_api.services import get_llm_client
                    LLMClient = get_llm_client()
                    llm_client = LLMClient()
                    recommendation = llm_client.recommend_option_to_sell(
                        symbol=symbol,
                        current_price=float(current_price),
                        candidates=sell_candidates
                    )
                    if recommendation:
                        recommendation = self._attach_nearest_candidate(
                            recommendation, sell_candidates
                        )
                    else:
                        recommendation_error = (
                            getattr(llm_client, 'last_error', None)
                            or 'LLM returned no recommendation'
                        )
                except Exception as e:
                    recommendation_error = str(e)
                    logger.warning(f"Option recommendation failed for {symbol}: {e}")

                # Always provide a recommendation object for UI continuity.
                if recommendation is None:
                    recommendation = self._heuristic_sell_recommendation(
                        symbol=symbol,
                        current_price=float(current_price),
                        candidates=sell_candidates
                    )
                    if recommendation and recommendation_error:
                        compact_error = str(recommendation_error).strip().replace('\n', ' ')
                        if len(compact_error) > 220:
                            compact_error = compact_error[:217] + '...'
                        recommendation['reasoning'] = (
                            recommendation['reasoning'] +
                            f" LLM unavailable: {compact_error}"
                        )

            elapsed = time.time() - start_time
            logger.info(
                f"OptionChainView.get completed in {elapsed:.2f}s: "
                f"{symbol} ${strike} {option_type}, {len(options_data)} expirations"
            )

            if with_recommendation:
                recommendation_source = None
                if recommendation:
                    recommendation_source = recommendation.get('generated_by', 'llm')
                recommendation_status = 'no_response'
                if recommendation_source == 'heuristic':
                    recommendation_status = 'fallback'
                elif recommendation:
                    recommendation_status = 'success'
                record_agent_run(
                    run_type='option_chain',
                    status=recommendation_status,
                    start_time=start_time,
                    message='Option recommendation generated',
                    llm_ok=not bool(recommendation_error),
                    llm_error=recommendation_error or '',
                    symbol=symbol,
                    option_type=str(recommendation.get('option_type', '')) if recommendation else None,
                    strike=recommendation.get('strike') if recommendation else strike,
                    recommendation_source=recommendation_source,
                    recommendation_candidates=len(sell_candidates),
                    details={
                        'requested_option_type': option_type,
                        'requested_strike': strike,
                        'expirations_returned': len(options_data),
                    },
                )

            return Response({
                'symbol': symbol,
                'strike': strike,
                'type': option_type,
                'current_price': current_price,
                'options': options_data,
                'count': len(options_data),
                'sell_recommendation': recommendation,
                'recommendation_error': recommendation_error,
                'recommendation_candidates': len(sell_candidates),
            })

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"OptionChainView.get failed in {elapsed:.2f}s: {e}", exc_info=True)
            if with_recommendation:
                record_agent_run(
                    run_type='option_chain',
                    status='error',
                    start_time=start_time,
                    message='Option chain failed',
                    llm_ok=False,
                    llm_error=str(e),
                    symbol=symbol,
                    option_type=option_type.upper(),
                    strike=strike_str,
                )
            return Response({'error': f'Failed to fetch option chain: {str(e)}'}, status=500)


class CollarStrategyView(APIView):
    """Calculate zero-cost collar strategies across all expirations."""

    permission_classes = [AllowAny]  # Public endpoint using free yfinance data

    def get(self, request):
        start_time = time.time()

        symbol = request.GET.get('symbol', '').upper()
        upside_pct_str = request.GET.get('upside_pct', '5')

        if not symbol:
            return Response({'error': 'symbol parameter is required'}, status=400)

        try:
            upside_pct = float(upside_pct_str)
        except ValueError:
            return Response({'error': 'upside_pct must be a valid number'}, status=400)

        if upside_pct <= 0 or upside_pct > 50:
            return Response({'error': 'upside_pct must be between 0 and 50'}, status=400)

        logger.info(f"CollarStrategyView.get: {symbol} upside={upside_pct}%")

        try:
            import yfinance as yf
            from datetime import datetime as dt

            ticker = yf.Ticker(symbol)

            # Current stock price
            current_price = None
            try:
                info = ticker.info
                current_price = info.get('regularMarketPrice') or info.get('currentPrice')
                if not current_price:
                    hist = ticker.history(period='1d')
                    current_price = float(hist['Close'].iloc[-1]) if len(hist) > 0 else None
            except Exception as e:
                logger.warning(f"CollarStrategyView: could not get price for {symbol}: {e}")

            if not current_price:
                return Response(
                    {'error': f'Could not retrieve current price for {symbol}'},
                    status=404,
                )

            # Target call strike
            call_strike_target = current_price * (1 + upside_pct / 100)

            # All expiration dates
            try:
                expirations = ticker.options
            except Exception:
                return Response(
                    {'error': f'No options data available for {symbol}'},
                    status=404,
                )

            if not expirations:
                return Response(
                    {'error': f'No option expirations found for {symbol}'},
                    status=404,
                )

            logger.info(f"CollarStrategyView: {len(expirations)} expirations for {symbol}")

            collars = []

            for exp_date in expirations:
                try:
                    chain = ticker.option_chain(exp_date)
                    calls_df = chain.calls
                    puts_df = chain.puts

                    if calls_df.empty or puts_df.empty:
                        continue

                    # Find call closest to target strike
                    call_idx = (calls_df['strike'] - call_strike_target).abs().idxmin()
                    call_row = calls_df.loc[call_idx]
                    call_strike = float(call_row['strike'])

                    # Use mid price for call premium (we SELL this)
                    call_bid = float(call_row.get('bid', 0) or 0)
                    call_ask = float(call_row.get('ask', 0) or 0)
                    call_last = float(call_row.get('lastPrice', 0) or 0)
                    call_premium = (call_bid + call_ask) / 2 if (call_bid > 0 and call_ask > 0) else call_last

                    if call_premium <= 0:
                        continue

                    # Filter OTM puts (strike <= current_price)
                    otm_puts = puts_df[puts_df['strike'] <= current_price].copy()
                    if otm_puts.empty:
                        continue

                    # Compute mid price for each put
                    otm_puts = otm_puts.copy()
                    otm_puts.loc[:, 'put_bid'] = otm_puts['bid'].fillna(0).astype(float)
                    otm_puts.loc[:, 'put_ask'] = otm_puts['ask'].fillna(0).astype(float)
                    otm_puts.loc[:, 'put_last'] = otm_puts['lastPrice'].fillna(0).astype(float)
                    otm_puts.loc[:, 'mid_price'] = otm_puts.apply(
                        lambda r: (r['put_bid'] + r['put_ask']) / 2
                        if r['put_bid'] > 0 and r['put_ask'] > 0
                        else r['put_last'],
                        axis=1
                    )

                    # Filter out zero-premium puts
                    otm_puts = otm_puts[otm_puts['mid_price'] > 0]
                    if otm_puts.empty:
                        continue

                    # Find put with premium closest to call premium (zero-cost match)
                    otm_puts.loc[:, 'premium_diff'] = (otm_puts['mid_price'] - call_premium).abs()
                    best_put_idx = otm_puts['premium_diff'].idxmin()
                    put_row = otm_puts.loc[best_put_idx]

                    put_strike = float(put_row['strike'])
                    put_bid = float(put_row['put_bid'])
                    put_ask = float(put_row['put_ask'])
                    put_premium = float(put_row['mid_price'])

                    # Calculations
                    # Net cost: put premium (we pay) - call premium (we collect)
                    # Negative = credit, Positive = debit
                    net_cost = round(put_premium - call_premium, 4)
                    max_profit = round(call_strike - current_price - net_cost, 2)
                    max_loss = round(put_strike - current_price - net_cost, 2)
                    protection_pct = round(((put_strike - current_price) / current_price) * 100, 2)
                    upside_cap_pct = round(((call_strike - current_price) / current_price) * 100, 2)

                    exp_datetime = dt.strptime(exp_date, '%Y-%m-%d')
                    days_to_expiry = (exp_datetime - dt.now()).days

                    collars.append({
                        'expiration': exp_date,
                        'days_to_expiry': days_to_expiry,
                        'call_strike': call_strike,
                        'call_premium': round(call_premium, 2),
                        'call_bid': call_bid,
                        'call_ask': call_ask,
                        'put_strike': put_strike,
                        'put_premium': round(put_premium, 2),
                        'put_bid': put_bid,
                        'put_ask': put_ask,
                        'net_cost': round(net_cost, 2),
                        'max_profit': max_profit,
                        'max_loss': max_loss,
                        'protection_pct': protection_pct,
                        'upside_cap_pct': upside_cap_pct,
                    })

                except Exception as e:
                    logger.warning(f"CollarStrategyView: error for {exp_date}: {e}")
                    continue

            collars.sort(key=lambda x: x['expiration'])

            elapsed = time.time() - start_time
            logger.info(
                f"CollarStrategyView.get completed in {elapsed:.2f}s: "
                f"{symbol} upside={upside_pct}%, {len(collars)} collars"
            )

            return Response({
                'symbol': symbol,
                'current_price': round(current_price, 2),
                'upside_pct': upside_pct,
                'call_strike_target': round(call_strike_target, 2),
                'collars': collars,
                'count': len(collars),
            })

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"CollarStrategyView.get failed in {elapsed:.2f}s: {e}", exc_info=True)
            return Response({'error': f'Failed to calculate collar strategy: {str(e)}'}, status=500)


class TestTradeView(APIView):
    """Execute a test trade to verify trading functionality."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Place a small test trade.

        Body: {"symbol": "AAPL", "action": "BUY", "quantity": 1}
        """
        start_time = time.time()
        try:
            symbol = request.data.get('symbol', 'AAPL')
            action = request.data.get('action', 'BUY').upper()
            quantity = int(request.data.get('quantity', 1))

            logger.info(f"TestTradeView.post called: {action} {quantity} {symbol}")

            if action not in ['BUY', 'SELL']:
                return Response({'error': 'Action must be BUY or SELL'}, status=400)

            if quantity < 1 or quantity > 10:
                return Response({'error': 'Quantity must be between 1 and 10 for test trades'}, status=400)

            from trading_api.services import get_broker
            broker = get_broker()

            logger.info(f"TEST TRADE: {action} {quantity} {symbol}")

            # Place market order
            order = broker.place_market_order(
                symbol=symbol,
                qty=quantity,
                side=action.lower()
            )

            elapsed = time.time() - start_time
            if order:
                logger.info(
                    f"TEST TRADE SUCCESS in {elapsed:.2f}s: "
                    f"Order ID {order.id}, Status: {order.status}"
                )
                return Response({
                    'status': 'success',
                    'message': f'Test trade executed: {action} {quantity} {symbol}',
                    'order': {
                        'id': order.id,
                        'symbol': order.symbol,
                        'side': order.side,
                        'qty': order.qty,
                        'status': order.status,
                        'filled_qty': order.filled_qty,
                        'filled_price': order.filled_price,
                    }
                })
            else:
                logger.error(f"TEST TRADE FAILED in {elapsed:.2f}s: order returned None")
                return Response({
                    'status': 'failed',
                    'message': 'Order placement returned None'
                }, status=500)

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"TestTradeView.post failed in {elapsed:.2f}s: {e}", exc_info=True)
            return Response({'status': 'error', 'message': str(e)}, status=500)


class AnalyzeView(APIView):
    """Run trading analysis cycle - triggered by Cloud Scheduler."""

    permission_classes = [AllowAny]  # Called by Cloud Scheduler

    def post(self, request):
        start_time = time.time()
        logger.info("AnalyzeView.post called")
        try:
            from trading_api.services import (
                get_trading_analyst,
                get_order_manager,
                get_slack
            )
            TradingAnalyst = get_trading_analyst()
            OrderManager = get_order_manager()
            _, notify_trade = get_slack()

            trading_client = get_trading_client()
            effective_settings = apply_runtime_trading_settings()
            settings_snapshot = build_runtime_settings_snapshot(effective_settings)

            # Respect configured analysis interval even if scheduler triggers more frequently.
            from trading_api.models.trade import AgentRunLog
            analysis_interval_minutes = int(effective_settings.get('analysis_interval', 15))
            last_analyze_run = AgentRunLog.objects.filter(
                run_type='analyze'
            ).exclude(
                status='skipped'
            ).order_by('-created_at').first()
            if last_analyze_run:
                elapsed_since_last = timezone.now() - last_analyze_run.created_at
                min_interval = timedelta(minutes=analysis_interval_minutes)
                if elapsed_since_last < min_interval:
                    remaining_seconds = int((min_interval - elapsed_since_last).total_seconds())
                    message = (
                        f"Analyze interval not reached; "
                        f"next run in ~{remaining_seconds}s"
                    )
                    logger.info(f"AnalyzeView: {message}")
                    record_agent_run(
                        run_type='analyze',
                        status='skipped',
                        start_time=start_time,
                        message=message,
                        market_open=trading_client.is_market_open(),
                        llm_ok=None,
                        trades_recommended=0,
                        trades_executed=0,
                        details={'settings': settings_snapshot, 'skip_reason': 'analysis_interval'},
                    )
                    return Response({
                        'status': 'skipped',
                        'message': message,
                        'analysis_interval_minutes': analysis_interval_minutes,
                        'next_run_in_seconds': remaining_seconds,
                    })

            # Check if market is open
            if not trading_client.is_market_open():
                elapsed = time.time() - start_time
                logger.info(f"AnalyzeView: market closed, skipping ({elapsed:.2f}s)")
                record_agent_run(
                    run_type='analyze',
                    status='skipped',
                    start_time=start_time,
                    message='Market is closed',
                    market_open=False,
                    llm_ok=None,
                    trades_recommended=0,
                    trades_executed=0,
                    details={'settings': settings_snapshot, 'skip_reason': 'market_closed'},
                )
                return Response({
                    'status': 'skipped',
                    'message': 'Market is closed'
                })

            # Run analysis
            analyst = TradingAnalyst()
            order_manager = OrderManager()

            account = trading_client.get_account()
            positions = trading_client.get_positions()

            response = analyst.analyze_and_recommend(
                cash=account['cash'],
                portfolio_value=account['portfolio_value'],
                positions=positions
            )

            if not response:
                elapsed = time.time() - start_time
                logger.info(f"AnalyzeView: no LLM response ({elapsed:.2f}s)")
                llm_error = getattr(analyst.llm_client, 'last_error', '') if analyst else ''
                record_agent_run(
                    run_type='analyze',
                    status='no_response',
                    start_time=start_time,
                    message='No LLM response',
                    market_open=True,
                    llm_ok=False,
                    llm_error=llm_error,
                    trades_recommended=0,
                    trades_executed=0,
                    details={'settings': settings_snapshot},
                )
                return Response({'status': 'no_response', 'message': 'No LLM response'})

            # Filter and execute trades
            valid_trades = analyst.filter_by_confidence(
                response.trades,
                min_confidence=float(effective_settings['min_confidence']) / 100.0
            )

            if not valid_trades:
                elapsed = time.time() - start_time
                logger.info(
                    f"AnalyzeView: no high-confidence trades ({elapsed:.2f}s)"
                )
                record_agent_run(
                    run_type='analyze',
                    status='no_trades',
                    start_time=start_time,
                    message='No high-confidence trades',
                    market_open=True,
                    llm_ok=True,
                    trades_recommended=len(response.trades),
                    trades_executed=0,
                    details={
                        'analysis_summary': response.analysis_summary,
                        'settings': settings_snapshot,
                    },
                )
                return Response({
                    'status': 'no_trades',
                    'message': 'No high-confidence trades',
                    'analysis': response.analysis_summary
                })

            # Execute trades
            executed = order_manager.execute_trades(valid_trades)
            executed_count = count_countable_trades(executed)
            executed_order_ids = [
                str(order.get('id'))
                for order in executed
                if order and is_countable_trade_record(order) and order.get('id')
            ]

            # Send Slack notifications
            for trade in valid_trades:
                notify_trade({
                    'action': trade.action,
                    'symbol': trade.symbol,
                    'quantity': trade.quantity,
                    'confidence': trade.confidence,
                    'reasoning': trade.reasoning
                })

            elapsed = time.time() - start_time
            logger.info(
                f"AnalyzeView.post completed in {elapsed:.2f}s: "
                f"{executed_count} trades executed"
            )

            record_agent_run(
                run_type='analyze',
                status='success',
                start_time=start_time,
                message=f"{executed_count} trades executed",
                market_open=True,
                llm_ok=True,
                trades_recommended=len(valid_trades),
                trades_executed=executed_count,
                details={
                    'analysis_summary': response.analysis_summary,
                    'settings': settings_snapshot,
                    'executed_order_ids': executed_order_ids,
                    'raw_execute_results': len(executed),
                },
            )

            return Response({
                'status': 'success',
                'trades_executed': executed_count,
                'trades': [
                    {'symbol': t.symbol, 'action': t.action, 'quantity': t.quantity}
                    for t in valid_trades
                ],
                'analysis': response.analysis_summary
            })

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"AnalyzeView.post failed in {elapsed:.2f}s: {e}")
            record_agent_run(
                run_type='analyze',
                status='error',
                start_time=start_time,
                message='Analyze run failed',
                llm_ok=False,
                llm_error=str(e),
                details={
                    'settings': build_runtime_settings_snapshot(
                        apply_runtime_trading_settings()
                    )
                },
            )
            return Response({'status': 'error', 'message': str(e)}, status=500)


class DailySummaryView(APIView):
    """Send daily trading summary email - triggered by Cloud Scheduler at market close."""

    permission_classes = [AllowAny]  # Called by Cloud Scheduler

    def post(self, request):
        start_time = time.time()
        logger.info("DailySummaryView.post called")
        try:
            from datetime import date
            from src.utils.email_notifier import send_daily_summary, email_notifier
            from trading_api.services import get_slack

            trading_client = get_trading_client()
            apply_runtime_trading_settings()
            risk_manager = get_risk_manager()

            # Get portfolio data
            account = trading_client.get_account()
            positions = trading_client.get_positions()

            if not account:
                elapsed = time.time() - start_time
                logger.error(f"DailySummaryView: account unavailable ({elapsed:.2f}s)")
                record_agent_run(
                    run_type='daily_summary',
                    status='error',
                    start_time=start_time,
                    message='Failed to get account',
                    llm_ok=None,
                )
                return Response({'status': 'error', 'message': 'Failed to get account'}, status=500)

            # Calculate daily change
            daily_change = account['equity'] - account['last_equity']
            daily_change_pct = (daily_change / account['last_equity'] * 100) if account['last_equity'] > 0 else 0

            portfolio = {
                'portfolio_value': account['portfolio_value'],
                'cash': account['cash'],
                'equity': account['equity'],
                'daily_change': daily_change,
                'daily_change_pct': daily_change_pct,
                'positions': positions,
            }

            # Get today's trades
            orders = trading_client.get_orders_history(limit=50)
            today = date.today().isoformat()
            trades_today = []
            for order in orders:
                created = order.get('created_at', '')
                if created and today in str(created):
                    trades_today.append({
                        'action': order.get('side', '').upper(),
                        'symbol': order.get('symbol'),
                        'quantity': order.get('qty'),
                        'filled_price': order.get('filled_avg_price'),
                        'created_at': created,
                        'confidence': 0.8,
                    })

            # Get risk status
            risk_status = risk_manager.get_risk_status(account)

            operations_summary = build_operations_summary(days=7)
            analysis_runs = int(operations_summary.get('today', {}).get('analyze_runs', 0))

            # Send email
            email_sent = send_daily_summary(
                portfolio,
                trades_today,
                analysis_runs,
                risk_status,
                operations_summary=operations_summary,
            )

            # Also send to Slack
            _, notify_portfolio = get_slack()
            notify_portfolio({
                'portfolio_value': portfolio['portfolio_value'],
                'daily_change': daily_change,
                'daily_change_pct': daily_change_pct,
                'positions_count': len(positions),
            })

            elapsed = time.time() - start_time
            logger.info(
                f"DailySummaryView.post completed in {elapsed:.2f}s: "
                f"email_sent={email_sent}, trades_today={len(trades_today)}"
            )

            record_agent_run(
                run_type='daily_summary',
                status='success' if email_sent else 'error',
                start_time=start_time,
                message='Daily summary email processed',
                llm_ok=None,
                trades_recommended=analysis_runs,
                trades_executed=len(trades_today),
                details={
                    'email_sent': bool(email_sent),
                    'email_enabled': bool(email_notifier.enabled),
                    'recipients_configured': len(email_notifier.to_emails),
                    'portfolio_value': account['portfolio_value'],
                    'operations_today': operations_summary.get('today', {}),
                },
            )

            return Response({
                'status': 'success',
                'email_sent': email_sent,
                'email_enabled': bool(email_notifier.enabled),
                'email_recipients_configured': len(email_notifier.to_emails),
                'portfolio_value': account['portfolio_value'],
                'daily_change': daily_change,
                'daily_change_pct': daily_change_pct,
                'trades_today': len(trades_today),
                'positions': len(positions),
                'operations_today': operations_summary.get('today', {}),
            })

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"DailySummaryView.post failed in {elapsed:.2f}s: {e}", exc_info=True)
            record_agent_run(
                run_type='daily_summary',
                status='error',
                start_time=start_time,
                message='Daily summary failed',
                llm_ok=None,
                llm_error=str(e),
            )
            return Response({'status': 'error', 'message': str(e)}, status=500)

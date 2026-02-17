"""Plaid service helpers for read-only ingestion (manual sync only)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import requests
from django.db import transaction
from django.utils import timezone


@dataclass
class PlaidErrorInfo:
    """Normalized Plaid API error payload."""

    message: str
    error_code: str = ''
    error_type: str = ''
    request_id: str = ''
    status_code: int = 0
    raw: Optional[Dict[str, Any]] = None


class PlaidServiceError(Exception):
    """Application-level Plaid exception."""

    def __init__(self, info: PlaidErrorInfo):
        super().__init__(info.message)
        self.info = info


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _to_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _to_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).replace('Z', '+00:00')
        return datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None


class PlaidClient:
    """Thin HTTP client for Plaid API."""

    BASE_URLS = {
        'sandbox': 'https://sandbox.plaid.com',
        'development': 'https://development.plaid.com',
        'production': 'https://production.plaid.com',
    }

    def __init__(self):
        self.client_id = os.environ.get('PLAID_CLIENT_ID', '').strip()
        self.secret = os.environ.get('PLAID_SECRET', '').strip()
        self.env = os.environ.get('PLAID_ENV', 'sandbox').strip().lower() or 'sandbox'
        self.redirect_uri = os.environ.get('PLAID_REDIRECT_URI', '').strip()
        self.base_url = self.BASE_URLS.get(self.env, self.BASE_URLS['sandbox'])
        self.timeout_seconds = int(os.environ.get('PLAID_TIMEOUT_SECONDS', '45'))

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.secret)

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_configured:
            raise PlaidServiceError(
                PlaidErrorInfo(
                    message='Plaid is not configured. Set PLAID_CLIENT_ID and PLAID_SECRET.',
                )
            )

        body = {
            'client_id': self.client_id,
            'secret': self.secret,
        }
        body.update(payload or {})
        url = f'{self.base_url}{path}'

        try:
            response = requests.post(url, json=body, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise PlaidServiceError(
                PlaidErrorInfo(
                    message=f'Plaid request failed: {exc}',
                )
            ) from exc

        data = {}
        try:
            data = response.json()
        except ValueError:
            pass

        if response.status_code >= 400:
            raise PlaidServiceError(
                PlaidErrorInfo(
                    message=data.get('error_message') or f'Plaid request failed with status {response.status_code}.',
                    error_code=data.get('error_code', ''),
                    error_type=data.get('error_type', ''),
                    request_id=data.get('request_id', ''),
                    status_code=response.status_code,
                    raw=data or None,
                )
            )

        return data

    def create_link_token(self, user_id: str, mode: str = 'investments') -> Dict[str, Any]:
        mode = (mode or 'investments').lower().strip()
        if mode not in {'investments', 'bank'}:
            mode = 'investments'

        if mode == 'investments':
            products = ['investments']
            optional_products = ['transactions']
        else:
            products = ['transactions']
            optional_products = ['auth']

        payload: Dict[str, Any] = {
            'client_name': 'LLM Trading Agent',
            'language': 'en',
            'country_codes': ['US'],
            'user': {'client_user_id': str(user_id)},
            'products': products,
            'optional_products': optional_products,
        }
        if self.redirect_uri:
            payload['redirect_uri'] = self.redirect_uri
        return self._post('/link/token/create', payload)

    def exchange_public_token(self, public_token: str) -> Dict[str, Any]:
        return self._post('/item/public_token/exchange', {'public_token': public_token})

    def get_item(self, access_token: str) -> Dict[str, Any]:
        return self._post('/item/get', {'access_token': access_token})

    def get_accounts(self, access_token: str) -> Dict[str, Any]:
        return self._post('/accounts/get', {'access_token': access_token})

    def get_institution_name(self, institution_id: str) -> str:
        if not institution_id:
            return ''
        data = self._post('/institutions/get_by_id', {
            'institution_id': institution_id,
            'country_codes': ['US'],
        })
        institution = data.get('institution') or {}
        return institution.get('name', '') or ''

    def remove_item(self, access_token: str) -> Dict[str, Any]:
        return self._post('/item/remove', {'access_token': access_token})

    def get_investment_holdings(self, access_token: str) -> Dict[str, Any]:
        return self._post('/investments/holdings/get', {'access_token': access_token})

    def get_investment_transactions(self, access_token: str, days: int = 730) -> List[Dict[str, Any]]:
        end_date = timezone.localdate()
        start_date = end_date - timedelta(days=max(1, days))

        count = 100
        offset = 0
        all_transactions: List[Dict[str, Any]] = []

        while True:
            data = self._post('/investments/transactions/get', {
                'access_token': access_token,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'options': {
                    'count': count,
                    'offset': offset,
                },
            })
            chunk = data.get('investment_transactions') or []
            total = int(data.get('total_investment_transactions') or 0)
            all_transactions.extend(chunk)

            offset += len(chunk)
            if offset >= total or not chunk:
                break

        return all_transactions


def _sync_accounts(item, accounts: List[Dict[str, Any]]) -> int:
    from trading_api.models import PlaidAccount

    seen_account_ids = set()
    synced_count = 0

    for account in accounts:
        account_id = account.get('account_id')
        if not account_id:
            continue

        balances = account.get('balances') or {}
        defaults = {
            'item': item,
            'name': account.get('name') or '',
            'official_name': account.get('official_name') or '',
            'mask': account.get('mask') or '',
            'account_type': account.get('type') or '',
            'subtype': account.get('subtype') or '',
            'verification_status': account.get('verification_status') or '',
            'current_balance': _to_decimal(balances.get('current')),
            'available_balance': _to_decimal(balances.get('available')),
            'limit_balance': _to_decimal(balances.get('limit')),
            'iso_currency_code': balances.get('iso_currency_code') or '',
            'unofficial_currency_code': balances.get('unofficial_currency_code') or '',
            'raw': account,
            'last_sync_at': timezone.now(),
        }
        PlaidAccount.objects.update_or_create(
            account_id=account_id,
            defaults=defaults,
        )
        seen_account_ids.add(account_id)
        synced_count += 1

    PlaidAccount.objects.filter(item=item).exclude(account_id__in=seen_account_ids).delete()
    return synced_count


def _sync_investments(item, holdings_response: Dict[str, Any], transactions: List[Dict[str, Any]]) -> Dict[str, int]:
    from trading_api.models import (
        PlaidAccount,
        PlaidHolding,
        PlaidInvestmentTransaction,
        PlaidSecurity,
    )

    securities = holdings_response.get('securities') or []
    holdings = holdings_response.get('holdings') or []

    account_map = {a.account_id: a for a in PlaidAccount.objects.filter(item=item)}
    security_map = {}
    for sec in securities:
        security_id = sec.get('security_id')
        if not security_id:
            continue
        obj, _ = PlaidSecurity.objects.update_or_create(
            item=item,
            security_id=security_id,
            defaults={
                'ticker_symbol': sec.get('ticker_symbol') or '',
                'name': sec.get('name') or '',
                'security_type': sec.get('type') or '',
                'close_price': _to_decimal(sec.get('close_price')),
                'close_price_as_of': _to_date(sec.get('close_price_as_of')),
                'iso_currency_code': sec.get('iso_currency_code') or '',
                'unofficial_currency_code': sec.get('unofficial_currency_code') or '',
                'raw': sec,
            },
        )
        security_map[security_id] = obj

    PlaidHolding.objects.filter(item=item).delete()
    holdings_synced = 0
    for holding in holdings:
        account_id = holding.get('account_id')
        security_id = holding.get('security_id')
        account = account_map.get(account_id)
        if not account:
            continue
        PlaidHolding.objects.create(
            item=item,
            account=account,
            security=security_map.get(security_id),
            quantity=_to_decimal(holding.get('quantity')),
            institution_price=_to_decimal(holding.get('institution_price')),
            institution_value=_to_decimal(holding.get('institution_value')),
            cost_basis=_to_decimal(holding.get('cost_basis')),
            iso_currency_code=holding.get('iso_currency_code') or '',
            unofficial_currency_code=holding.get('unofficial_currency_code') or '',
            raw=holding,
        )
        holdings_synced += 1

    transactions_synced = 0
    for tx in transactions:
        tx_id = tx.get('investment_transaction_id')
        if not tx_id:
            continue
        account_id = tx.get('account_id')
        security_id = tx.get('security_id')
        PlaidInvestmentTransaction.objects.update_or_create(
            investment_transaction_id=tx_id,
            defaults={
                'item': item,
                'account': account_map.get(account_id),
                'security': security_map.get(security_id),
                'name': tx.get('name') or '',
                'ticker_symbol': tx.get('ticker_symbol') or '',
                'tx_type': tx.get('type') or '',
                'subtype': tx.get('subtype') or '',
                'amount': _to_decimal(tx.get('amount')),
                'price': _to_decimal(tx.get('price')),
                'quantity': _to_decimal(tx.get('quantity')),
                'fees': _to_decimal(tx.get('fees')),
                'date': _to_date(tx.get('date')),
                'datetime': _to_datetime(tx.get('datetime')),
                'cancel_transaction_id': tx.get('cancel_transaction_id') or '',
                'iso_currency_code': tx.get('iso_currency_code') or '',
                'unofficial_currency_code': tx.get('unofficial_currency_code') or '',
                'raw': tx,
            },
        )
        transactions_synced += 1

    return {
        'holdings': holdings_synced,
        'transactions': transactions_synced,
    }


def sync_item_data(item, triggered_by=None) -> Dict[str, Any]:
    """Run manual sync for one Plaid item."""

    from trading_api.models import PlaidSyncLog

    started_monotonic = time.time()
    sync_log = PlaidSyncLog.objects.create(
        item=item,
        triggered_by=triggered_by,
        status='error',
        message='Sync started',
        details={},
    )

    client = PlaidClient()
    if not client.is_configured:
        msg = 'Plaid is not configured. Set PLAID_CLIENT_ID and PLAID_SECRET.'
        item.status = 'error'
        item.last_error = msg
        item.last_sync_at = timezone.now()
        item.save(update_fields=['status', 'last_error', 'last_sync_at', 'updated_at'])
        sync_log.message = msg
        sync_log.ended_at = timezone.now()
        sync_log.duration_ms = int((time.time() - started_monotonic) * 1000)
        sync_log.save(update_fields=['message', 'ended_at', 'duration_ms'])
        raise PlaidServiceError(PlaidErrorInfo(message=msg))

    try:
        with transaction.atomic():
            accounts_response = client.get_accounts(item.access_token)
            account_count = _sync_accounts(item, accounts_response.get('accounts') or [])

            holdings_count = 0
            transaction_count = 0
            if item.product_type == 'investments':
                holdings_response = client.get_investment_holdings(item.access_token)
                transactions = client.get_investment_transactions(item.access_token)
                inv_counts = _sync_investments(item, holdings_response, transactions)
                holdings_count = inv_counts['holdings']
                transaction_count = inv_counts['transactions']

            now = timezone.now()
            item.status = 'active'
            item.last_error = ''
            item.last_sync_at = now
            item.last_success_at = now
            item.save(update_fields=['status', 'last_error', 'last_sync_at', 'last_success_at', 'updated_at'])

            sync_log.status = 'success'
            sync_log.message = 'Manual sync completed.'
            sync_log.accounts_synced = account_count
            sync_log.holdings_synced = holdings_count
            sync_log.transactions_synced = transaction_count
            sync_log.details = {
                'product_type': item.product_type,
            }
            sync_log.ended_at = now
            sync_log.duration_ms = int((time.time() - started_monotonic) * 1000)
            sync_log.save(
                update_fields=[
                    'status',
                    'message',
                    'accounts_synced',
                    'holdings_synced',
                    'transactions_synced',
                    'details',
                    'ended_at',
                    'duration_ms',
                ]
            )

            return {
                'accounts_synced': account_count,
                'holdings_synced': holdings_count,
                'transactions_synced': transaction_count,
                'duration_ms': sync_log.duration_ms,
            }
    except PlaidServiceError as exc:
        status = 'login_required' if exc.info.error_code == 'ITEM_LOGIN_REQUIRED' else 'error'
        item.status = status
        item.last_error = exc.info.message
        item.last_sync_at = timezone.now()
        item.save(update_fields=['status', 'last_error', 'last_sync_at', 'updated_at'])

        sync_log.status = 'error'
        sync_log.message = exc.info.message
        sync_log.details = {
            'error_code': exc.info.error_code,
            'error_type': exc.info.error_type,
            'request_id': exc.info.request_id,
        }
        sync_log.ended_at = timezone.now()
        sync_log.duration_ms = int((time.time() - started_monotonic) * 1000)
        sync_log.save(update_fields=['status', 'message', 'details', 'ended_at', 'duration_ms'])
        raise


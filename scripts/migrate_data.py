#!/usr/bin/env python
"""
Data Migration Script: SQLite to Django (SQLite/PostgreSQL)

This script migrates existing data from the local SQLite database
(trading_history.db) to the new Django database.

Usage:
    # For local SQLite development:
    python scripts/migrate_data.py
    
    # For Cloud SQL (start proxy first):
    export DB_HOST=127.0.0.1
    python scripts/migrate_data.py
"""

import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings.development')

import django
django.setup()

from django.db import transaction
from trading_api.models import Trade, PortfolioSnapshot

# Suppress django-allauth deprecation warnings
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)


def get_sqlite_connection():
    """Connect to the existing SQLite database."""
    db_path = PROJECT_ROOT / 'trading_history.db'
    if not db_path.exists():
        print(f"❌ SQLite database not found at: {db_path}")
        sys.exit(1)
    
    print(f"📂 Connecting to SQLite: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row  # Enable dictionary-like access
    return conn


def migrate_trades(cursor):
    """Migrate trades from SQLite to Django database."""
    print("\n📊 Migrating trades...")
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
    if not cursor.fetchone():
        print("   No trades table found in SQLite")
        return
    
    # Get actual schema
    cursor.execute("PRAGMA table_info(trades)")
    columns = [col['name'] for col in cursor.fetchall()]
    print(f"   SQLite columns: {columns}")
    
    cursor.execute("SELECT * FROM trades ORDER BY id")
    
    migrated = 0
    skipped = 0
    
    for row in cursor.fetchall():
        row_dict = dict(row)
        
        # Check if trade already exists (by order_id if available)
        order_id = row_dict.get('order_id')
        if order_id and Trade.objects.filter(order_id=order_id).exists():
            skipped += 1
            continue
        
        # Map old schema to new schema
        try:
            trade = Trade.objects.create(
                symbol=row_dict.get('symbol', ''),
                action=row_dict.get('action', 'BUY'),
                quantity=row_dict.get('quantity', 0),
                price=Decimal(str(row_dict.get('executed_price') or row_dict.get('limit_price') or 0)),
                total_value=Decimal(str((row_dict.get('executed_price') or row_dict.get('limit_price') or 0) * row_dict.get('quantity', 0))),
                order_id=order_id,
                order_type=row_dict.get('order_type', 'market'),
                status=row_dict.get('status', 'executed'),
                confidence=row_dict.get('confidence'),
                reasoning=row_dict.get('reasoning') or row_dict.get('llm_analysis') or '',
            )
            migrated += 1
        except Exception as e:
            print(f"   ⚠️ Error migrating trade {order_id}: {e}")
            continue
    
    print(f"   ✅ Migrated: {migrated}, Skipped (already exists): {skipped}")


def migrate_portfolio_snapshots(cursor):
    """Migrate portfolio snapshots from SQLite to Django database."""
    print("\n📈 Migrating portfolio snapshots...")
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='portfolio_snapshots'")
    if not cursor.fetchone():
        print("   No portfolio_snapshots table found in SQLite")
        return
    
    # Get actual schema
    cursor.execute("PRAGMA table_info(portfolio_snapshots)")
    columns = [col['name'] for col in cursor.fetchall()]
    print(f"   SQLite columns: {columns}")
    
    cursor.execute("SELECT * FROM portfolio_snapshots ORDER BY id")
    
    migrated = 0
    
    for row in cursor.fetchall():
        row_dict = dict(row)
        
        try:
            PortfolioSnapshot.objects.create(
                portfolio_value=Decimal(str(row_dict.get('portfolio_value', 0))),
                cash=Decimal(str(row_dict.get('cash', 0))),
                equity=Decimal(str(row_dict.get('equity', 0))),
                daily_change=Decimal(str(row_dict.get('daily_change', 0))) if row_dict.get('daily_change') else None,
                daily_change_pct=row_dict.get('daily_change_pct'),
            )
            migrated += 1
        except Exception as e:
            print(f"   ⚠️ Error migrating snapshot: {e}")
            continue
    
    print(f"   ✅ Migrated: {migrated}")


def show_sqlite_tables(cursor):
    """Show all tables in SQLite database."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    print("\n📋 Tables in source SQLite database:")
    for table in tables:
        table_name = table['name']
        cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
        count = cursor.fetchone()['count']
        print(f"   - {table_name}: {count} rows")


def main():
    print("=" * 60)
    print("🔄 Data Migration: SQLite → Django Database")
    print("=" * 60)
    
    # Connect to source SQLite
    conn = get_sqlite_connection()
    cursor = conn.cursor()
    
    # Show existing tables
    show_sqlite_tables(cursor)
    
    # Migrate data in a transaction
    try:
        with transaction.atomic():
            migrate_trades(cursor)
            migrate_portfolio_snapshots(cursor)
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        conn.close()
        sys.exit(1)
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ Data migration completed successfully!")
    print("=" * 60)
    
    # Show final counts
    print(f"\n📊 Final counts in Django database:")
    print(f"   - Trades: {Trade.objects.count()}")
    print(f"   - Portfolio Snapshots: {PortfolioSnapshot.objects.count()}")


if __name__ == '__main__':
    main()

"""Cloud SQL database connection for user management."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from loguru import logger

# Base class for SQLAlchemy models
Base = declarative_base()

# Database configuration
DB_USER = os.getenv('DB_USER', 'trading_user')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'stock_trading')
DB_HOST = os.getenv('DB_HOST', 'localhost')
INSTANCE_CONNECTION_NAME = os.getenv('INSTANCE_CONNECTION_NAME', '')

# Create database URL
def get_database_url():
    """Get the database connection URL based on environment."""
    
    # For Cloud Run with Unix socket connection
    if INSTANCE_CONNECTION_NAME:
        socket_path = f"/cloudsql/{INSTANCE_CONNECTION_NAME}"
        return f"postgresql+pg8000://{DB_USER}:{DB_PASSWORD}@/{DB_NAME}?unix_sock={socket_path}/.s.PGSQL.5432"
    
    # For local development or direct connection
    if DB_HOST and DB_PASSWORD:
        return f"postgresql+pg8000://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:5432/{DB_NAME}"
    
    # Fallback to SQLite for local testing
    logger.warning("No database configured, using SQLite")
    return "sqlite:///./stock_trading.db"


# Create engine and session
engine = None
SessionLocal = None


def init_db():
    """Initialize the database connection and create tables."""
    global engine, SessionLocal
    
    try:
        db_url = get_database_url()
        logger.info(f"Connecting to database...")
        
        # Create engine with connection pooling
        engine = create_engine(
            db_url,
            pool_size=5,
            max_overflow=2,
            pool_timeout=30,
            pool_recycle=1800,  # Recycle connections after 30 minutes
        )
        
        # Create session factory
        SessionLocal = scoped_session(
            sessionmaker(autocommit=False, autoflush=False, bind=engine)
        )
        
        # Import all models and create tables
        from models.user import User
        from models.trade import Trade, PortfolioSnapshot
        from models.trading import Position, Order, Watchlist, AnalysisLog, TradingConfig
        Base.metadata.create_all(bind=engine)
        
        logger.info("Database initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False


def get_db():
    """Get a database session."""
    if SessionLocal is None:
        init_db()
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    """Get a database session (non-generator version)."""
    if SessionLocal is None:
        init_db()
    return SessionLocal()

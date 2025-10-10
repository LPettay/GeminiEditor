"""
Database configuration and session management for GeminiEditor.
Uses SQLAlchemy with SQLite for simplicity and portability.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import os
from typing import Generator
import logging

logger = logging.getLogger(__name__)

# Database file location
DATABASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATABASE_DIR, exist_ok=True)
DATABASE_PATH = os.path.join(DATABASE_DIR, "gemini_editor.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Create engine
# For SQLite, we use StaticPool and check_same_thread=False for FastAPI compatibility
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False  # Set to True for SQL debugging
)

# Enable foreign key constraints for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable foreign key constraints in SQLite."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all models
Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    """
    Dependency function to get database session.
    Use with FastAPI's Depends() for automatic session management.
    
    Example:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """
    Initialize the database by creating all tables.
    Call this on application startup.
    """
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully")

def reset_db():
    """
    Drop all tables and recreate them.
    WARNING: This will delete all data!
    Use only for development/testing.
    """
    logger.warning("Resetting database - all data will be lost!")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    logger.info("Database reset complete")


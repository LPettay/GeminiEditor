"""
Database initialization and migration utilities.
Run this script to set up the database for the first time.
"""

import sys
import os
from pathlib import Path

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import init_db, reset_db, DATABASE_PATH
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Initialize the database."""
    print("=" * 60)
    print("GeminiEditor Database Initialization")
    print("=" * 60)
    print(f"\nDatabase location: {DATABASE_PATH}")
    
    if os.path.exists(DATABASE_PATH):
        print(f"\nWARNING: Database file already exists at: {DATABASE_PATH}")
        response = input("Do you want to reset it? This will DELETE ALL DATA! (yes/no): ")
        if response.lower() == 'yes':
            print("\nResetting database...")
            reset_db()
            print("SUCCESS: Database reset successfully!")
        else:
            print("\nKeeping existing database.")
            print("Running init_db to create any missing tables...")
            init_db()
            print("SUCCESS: Database initialization complete!")
    else:
        print("\nCreating new database...")
        init_db()
        print("SUCCESS: Database created successfully!")
    
    print("\n" + "=" * 60)
    print("Database is ready to use!")
    print("=" * 60)


if __name__ == "__main__":
    main()


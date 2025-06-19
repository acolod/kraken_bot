# persistence/database.py - v0.1.0
import logging
import sqlite3 # Example, can be replaced with SQLAlchemy or other ORMs/DBs

logger = logging.getLogger(__name__)

DB_FILE = "kraken_bot_data.db"

class Database:
    """Handles database operations for persisting data."""
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        self.conn = None
        logger.info(f"Database module initialized with db_file: {db_file}")

    def connect(self):
        """Establishes a connection to the SQLite database."""
        self.conn = sqlite3.connect(self.db_file)
        logger.info(f"Connected to database: {self.db_file}")

    def close(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
            logger.info(f"Closed database connection: {self.db_file}")

    # Add methods for creating tables, storing trades, user preferences, etc.
    # Example:
    # def create_trades_table(self):
    #     if not self.conn: self.connect()
    #     cursor = self.conn.cursor()
    #     cursor.execute('''
    #         CREATE TABLE IF NOT EXISTS trades (
    #             id INTEGER PRIMARY KEY AUTOINCREMENT,
    #             pair TEXT,
    #             entry_price REAL,
    #             exit_price REAL,
    #             status TEXT
    #         )
    #     ''')
    #     self.conn.commit()
    #     logger.info("Trades table ensured.")
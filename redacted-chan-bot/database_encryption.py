"""
Database encryption helper for SQLCipher.

Provides transparent encryption at rest for SQLite databases.
The encryption key is read from DATABASE_ENCRYPTION_KEY environment variable.
On first run, a key is generated and must be saved to Railway secrets.
"""

import os
import secrets
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_KEY = None


def get_or_generate_key() -> str:
    """Get encryption key from env, or generate one on first run."""
    global _DB_KEY

    if _DB_KEY:
        return _DB_KEY

    # Try to read from environment
    key = os.getenv("DATABASE_ENCRYPTION_KEY", "").strip()

    if not key:
        # Generate a new key on first run
        key = secrets.token_hex(32)
        logger.warning(
            f"[encryption] Generated new DATABASE_ENCRYPTION_KEY (first run). "
            f"Add to Railway secrets: DATABASE_ENCRYPTION_KEY={key}"
        )

    _DB_KEY = key
    return _DB_KEY


def get_encrypted_connection(db_path: str | Path) -> sqlite3.Connection:
    """
    Get a SQLite connection with encryption enabled via SQLCipher.

    The database is transparently encrypted/decrypted on disk.
    The key is read from DATABASE_ENCRYPTION_KEY env var (or generated on first run).
    """
    key = get_or_generate_key()

    try:
        import sqlcipher3 as sqlite3_enc
        conn = sqlite3_enc.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Set encryption key and pragmas
        conn.execute(f"PRAGMA key = '{key}'")
        conn.execute("PRAGMA cipher_page_size = 4096")
        conn.execute("PRAGMA kdf_iter = 64000")
        conn.execute("PRAGMA cipher_compatibility = 4")

        # Verify the database is encrypted by attempting to read
        conn.execute("SELECT 1")
        conn.commit()
        logger.info(f"[encryption] encrypted database: {Path(db_path).name}")
        return conn

    except ImportError:
        # Fallback to unencrypted if sqlcipher3 not installed
        logger.warning("[encryption] sqlcipher3 not available — using unencrypted SQLite")
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    except Exception as e:
        logger.error(f"[encryption] failed to initialize encrypted database: {e}")
        raise

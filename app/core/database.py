"""SQLite connection management, migrations, and WAL configuration."""
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def get_db_path() -> Path:
    raw_path = os.getenv("DATABASE_PATH", "data/billing_engine.db")
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def init_db(db_path: Path | None = None):
    """Executes schema.sql migrations, enables foreign keys and WAL mode."""
    target_path = db_path or get_db_path()
    schema_file = Path(__file__).parent / "schema.sql"
    
    with sqlite3.connect(target_path, check_same_thread=False) as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        with open(schema_file, "r") as f:
            conn.executescript(f.read())
        conn.commit()

@contextmanager
def get_db_connection(db_path: Path | None = None):
    """Context manager for thread-safe SQLite connection."""
    target_path = db_path or get_db_path()
    conn = sqlite3.connect(target_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        conn.close()

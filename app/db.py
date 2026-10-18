import sqlite3
from pathlib import Path
from .config import settings

SCHEMA = Path(__file__).resolve().parent.parent / "migrations/001_initial.sql"

def connect():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.data_dir / "news.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def initialize():
    with connect() as conn:
        for migration in sorted(SCHEMA.parent.glob("*.sql")):
            conn.executescript(migration.read_text(encoding="utf-8"))

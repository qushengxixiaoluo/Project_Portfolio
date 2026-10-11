"""SQLite 存储层：项目、文件、分块、聊天记录。"""
import sqlite3
import time
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    summary TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    created_at REAL NOT NULL,
    intro TEXT DEFAULT '',
    intro_files INTEGER DEFAULT -1,
    intro_at REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    size INTEGER DEFAULT 0,
    kind TEXT DEFAULT '',
    uploaded_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        # 旧库迁移：补 intro 相关列
        cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)")}
        if "intro" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN intro TEXT DEFAULT ''")
        if "intro_files" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN intro_files INTEGER DEFAULT -1")
        if "intro_at" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN intro_at REAL DEFAULT 0")


def now() -> float:
    return time.time()

"""Long-term memory. `MemoryStore` is the interface the agent programs against;
`SQLiteMemoryStore` is the dumb-but-reliable v1. A vector backend
(sentence-transformers + sqlite-vec) can replace it later without touching the
agent loop — that seam is the whole point of this file's shape.
"""
from __future__ import annotations

import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from .paths import memory_db
from .log import get_logger

log = get_logger("atlas.memory")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY,
    fact TEXT NOT NULL,
    source TEXT DEFAULT 'user',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY,
    command TEXT NOT NULL,
    outcome TEXT,
    ok INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL,
    hour_bucket INTEGER NOT NULL,
    count INTEGER DEFAULT 0,
    UNIQUE(key, hour_bucket)
);
"""


class MemoryStore(ABC):
    @abstractmethod
    def remember(self, fact: str, source: str = "user") -> None: ...
    @abstractmethod
    def recall(self, query: str, limit: int = 5) -> list[str]: ...
    @abstractmethod
    def log_history(self, command: str, outcome: str, ok: bool = True) -> None: ...
    @abstractmethod
    def habit_tick(self, key: str) -> None: ...
    @abstractmethod
    def summary(self, max_facts: int = 8, max_habits: int = 5) -> str: ...
    @abstractmethod
    def close(self) -> None: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SQLiteMemoryStore(MemoryStore):
    """memory.db next to the exe. WAL mode; one connection per thread
    (sqlite3 connections are not thread-safe to share)."""

    def __init__(self, path=None):
        self.path = str(path or memory_db())
        self._local = threading.local()
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    def remember(self, fact, source="user"):
        fact = fact.strip()[:1000]
        if not fact:
            return
        with self._conn() as c:
            c.execute("INSERT INTO facts (fact, source, created_at) VALUES (?,?,?)",
                      (fact, source, _now()))
        log.info("fact stored: %s", fact)

    def recall(self, query, limit=5):
        # v1: LIKE search over each word. The vector backend replaces only this.
        words = [w for w in query.strip().split() if len(w) > 2][:5]
        if not words:
            words = [query.strip()]
        clauses = " OR ".join("fact LIKE ?" for _ in words)
        params = [f"%{w}%" for w in words]
        with self._conn() as c:
            rows = c.execute(
                f"SELECT fact FROM facts WHERE {clauses} ORDER BY id DESC LIMIT ?",
                (*params, limit)).fetchall()
        return [r[0] for r in rows]

    def log_history(self, command, outcome, ok=True):
        with self._conn() as c:
            c.execute("INSERT INTO history (command, outcome, ok, created_at) VALUES (?,?,?,?)",
                      (command[:2000], (outcome or "")[:2000], int(ok), _now()))

    def habit_tick(self, key):
        hour = datetime.now().hour
        with self._conn() as c:
            c.execute("""INSERT INTO habits (key, hour_bucket, count) VALUES (?,?,1)
                         ON CONFLICT(key, hour_bucket) DO UPDATE SET count = count + 1""",
                      (key[:200], hour))

    def summary(self, max_facts=8, max_habits=5):
        with self._conn() as c:
            facts = [r[0] for r in c.execute(
                "SELECT fact FROM facts ORDER BY id DESC LIMIT ?", (max_facts,))]
            habits = c.execute(
                """SELECT key, hour_bucket, count FROM habits
                   ORDER BY count DESC LIMIT ?""", (max_habits,)).fetchall()
        parts = []
        if facts:
            parts.append("Known facts about the user:\n" +
                         "\n".join(f"- {f}" for f in facts))
        if habits:
            parts.append("Observed habits (key @ hour ×count):\n" +
                         "\n".join(f"- {k} @ {h:02d}:00 ×{n}" for k, h, n in habits))
        return "\n".join(parts) if parts else "No stored memory yet."

    def close(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

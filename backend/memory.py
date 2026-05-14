import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


class MemoryStore:
    def __init__(self, db_path: str = "database/memory.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(content, content='memories', content_rowid='id');

                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            self.conn.commit()

    def add_memory(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> int:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO memories (content, metadata) VALUES (?, ?)",
                (content, json.dumps(metadata or {})),
            )
            row_id = cursor.lastrowid
            cursor.execute("INSERT INTO memory_fts(rowid, content) VALUES (?, ?)", (row_id, content))
            self.conn.commit()
        return int(row_id)

    def search_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT m.id, m.content, m.metadata, m.created_at
                FROM memory_fts f
                JOIN memories m ON m.id = f.rowid
                WHERE memory_fts MATCH ?
                ORDER BY bm25(memory_fts)
                LIMIT ?
                """,
                (query, limit),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "content": row["content"],
                "metadata": json.loads(row["metadata"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def add_message(self, role: str, message: str) -> None:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO conversations (role, message) VALUES (?, ?)",
                (role, message),
            )
            self.conn.commit()

    def recent_messages(self, limit: int = 12) -> List[Dict[str, str]]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT role, message FROM conversations ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
        return [{"role": row["role"], "content": row["message"]} for row in reversed(rows)]

    def set_preference(self, key: str, value: str) -> None:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO preferences(key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (key, value),
            )
            self.conn.commit()

    def get_preference(self, key: str) -> Optional[str]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT value FROM preferences WHERE key = ?", (key,))
            row = cursor.fetchone()
        return row["value"] if row else None

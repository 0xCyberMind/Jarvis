import sqlite3
import json
import threading
from typing import Any, Dict, List, Optional


class GraphDB:
    def __init__(self, path: str = "jarvis_graph.db"):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT,
                    type TEXT,
                    data TEXT,
                    created_at REAL DEFAULT (strftime('%s','now'))
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    src INTEGER,
                    dst INTEGER,
                    relation TEXT,
                    data TEXT,
                    created_at REAL DEFAULT (strftime('%s','now'))
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_nodes_label ON nodes(label)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst)")
            self._conn.commit()

    def add_node(self, label: str, type: str = "entity", data: Optional[Dict[str, Any]] = None) -> int:
        data = data or {}
        j = json.dumps(data, default=str)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("INSERT INTO nodes(label, type, data) VALUES (?, ?, ?)", (label, type, j))
            self._conn.commit()
            return cur.lastrowid

    def upsert_node(self, label: str, type: str = "entity", data: Optional[Dict[str, Any]] = None) -> int:
        data = data or {}
        j = json.dumps(data, default=str)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT id FROM nodes WHERE label = ? AND type = ? ORDER BY id DESC LIMIT 1", (label, type))
            row = cur.fetchone()
            if row:
                node_id = int(row[0])
                cur.execute("UPDATE nodes SET data = ?, created_at = strftime('%s','now') WHERE id = ?", (j, node_id))
                self._conn.commit()
                return node_id
            cur.execute("INSERT INTO nodes(label, type, data) VALUES (?, ?, ?)", (label, type, j))
            self._conn.commit()
            return cur.lastrowid

    def clear_nodes(self, type: Optional[str] = None, label_prefix: Optional[str] = None) -> int:
        sql = "DELETE FROM nodes"
        where: List[str] = []
        params: List[Any] = []
        if type:
            where.append("type = ?")
            params.append(type)
        if label_prefix:
            where.append("label LIKE ?")
            params.append(f"{label_prefix}%")
        if where:
            sql += " WHERE " + " AND ".join(where)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            deleted = cur.rowcount if cur.rowcount is not None else 0
            self._conn.commit()
        return int(deleted)

    def search_nodes(self, query: str, type: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []
        terms = [term for term in query.split() if len(term) > 1][:8]
        if not terms:
            terms = [query]
        clauses = []
        params: List[Any] = []
        for term in terms:
            like = f"%{term}%"
            clauses.append("(label LIKE ? OR data LIKE ?)")
            params.extend([like, like])
        sql = "SELECT id, label, type, data, created_at FROM nodes"
        where: List[str] = []
        if clauses:
            where.append("(" + " OR ".join(clauses) + ")")
        if type:
            where.append("type = ?")
            params.append(type)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
        out = []
        for r in rows:
            try:
                data = json.loads(r[3]) if r[3] else {}
            except Exception:
                data = {"raw": r[3]}
            out.append({"id": r[0], "label": r[1], "type": r[2], "data": data, "created_at": r[4]})
        return out

    def add_edge(self, src: int, dst: int, relation: str = "related_to", data: Optional[Dict[str, Any]] = None) -> int:
        data = data or {}
        j = json.dumps(data, default=str)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("INSERT INTO edges(src, dst, relation, data) VALUES (?, ?, ?, ?)", (src, dst, relation, j))
            self._conn.commit()
            return cur.lastrowid

    def find_nodes(self, label: Optional[str] = None, type: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        sql = "SELECT id, label, type, data, created_at FROM nodes"
        where: List[str] = []
        params: List[Any] = []
        if label:
            where.append("label LIKE ?")
            params.append(f"%{label}%")
        if type:
            where.append("type = ?")
            params.append(type)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
        out = []
        for r in rows:
            try:
                data = json.loads(r[3]) if r[3] else {}
            except Exception:
                data = {"raw": r[3]}
            out.append({"id": r[0], "label": r[1], "type": r[2], "data": data, "created_at": r[4]})
        return out

    def neighbors(self, node_id: int, direction: str = "both", limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.cursor()
            if direction in ("out", "both"):
                cur.execute("SELECT dst, relation, data FROM edges WHERE src = ? LIMIT ?", (node_id, limit))
                out = cur.fetchall()
            else:
                out = []
            if direction in ("in", "both"):
                cur.execute("SELECT src, relation, data FROM edges WHERE dst = ? LIMIT ?", (node_id, limit))
                inn = cur.fetchall()
            else:
                inn = []
        results = []
        for r in out:
            try:
                d = json.loads(r[2]) if r[2] else {}
            except Exception:
                d = {"raw": r[2]}
            results.append({"node": r[0], "relation": r[1], "data": d})
        for r in inn:
            try:
                d = json.loads(r[2]) if r[2] else {}
            except Exception:
                d = {"raw": r[2]}
            results.append({"node": r[0], "relation": r[1], "data": d})
        return results

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

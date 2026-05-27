"""
PostgreSQL connection wrapper — sqlite3-like API for server.py compatibility.
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

from .pg_compat import adapt_sql, is_pragma


class PgRow:
    """Row compatible with sqlite3.Row indexing by name and position."""

    __slots__ = ("_mapping", "_values")

    def __init__(self, mapping: dict[str, Any]):
        self._mapping = dict(mapping)
        self._values = tuple(self._mapping.values())

    def __getitem__(self, key: int | str):
        if isinstance(key, int):
            return self._values[key]
        return self._mapping[key]

    def __iter__(self):
        return iter(self._values)

    def keys(self):
        return self._mapping.keys()

    def __len__(self) -> int:
        return len(self._values)


class PgCursor:
    __slots__ = ("_cur", "rowcount", "lastrowid")

    def __init__(self, cur: Any):
        self._cur = cur
        self.rowcount = getattr(cur, "rowcount", -1)
        self.lastrowid = None

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return PgRow(row)
        return PgRow(dict(zip([d[0] for d in self._cur.description], row)))

    def fetchall(self):
        rows = self._cur.fetchall()
        out = []
        for row in rows:
            if isinstance(row, dict):
                out.append(PgRow(row))
            else:
                out.append(PgRow(dict(zip([d[0] for d in self._cur.description], row))))
        return out

    def __iter__(self):
        while True:
            row = self.fetchone()
            if row is None:
                break
            yield row


class PgConnection:
    """Wraps psycopg connection with sqlite3.Connection-style methods."""

    def __init__(self, conn: Any, pool_cm: Any = None):
        self._conn = conn
        self._pool_cm = pool_cm

    def execute(self, sql: str, params: Sequence[Any] | None = None):
        if is_pragma(sql):
            return PgCursor(self._conn.execute("SELECT 1"))
        adapted = adapt_sql(sql)
        cur = self._conn.execute(adapted, params or ())
        return PgCursor(cur)

    def executemany(self, sql: str, params_seq: Iterable[Sequence[Any]]):
        adapted = adapt_sql(sql)
        cur = self._conn.cursor()
        cur.executemany(adapted, list(params_seq))
        return PgCursor(cur)

    def cursor(self):
        return self._conn.cursor()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        if self._pool_cm is not None:
            self._pool_cm.__exit__(None, None, None)
            self._pool_cm = None
        else:
            self._conn.close()

    def executescript(self, script: str) -> None:
        statements = [s.strip() for s in script.split(";") if s.strip()]
        for stmt in statements:
            if is_pragma(stmt):
                continue
            self.execute(stmt)

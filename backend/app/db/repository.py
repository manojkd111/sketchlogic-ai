"""SQLite persistence for the MVP (stdlib sqlite3, no ORM).

Schema migrations are tracked with `PRAGMA user_version`. Add a new entry to
`_MIGRATIONS` for every change; never edit an applied migration.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

_MIGRATIONS: list[str] = [
    # 1: uploads
    """
    CREATE TABLE uploads (
        id               TEXT PRIMARY KEY,
        original_name    TEXT NOT NULL,
        kind             TEXT NOT NULL,
        media_type       TEXT NOT NULL,
        size_bytes       INTEGER NOT NULL,
        sha256           TEXT NOT NULL,
        width            INTEGER,
        height           INTEGER,
        storage_path     TEXT NOT NULL,
        -- Private user data is NEVER used for training unless this is explicitly 1.
        training_consent INTEGER NOT NULL DEFAULT 0 CHECK (training_consent IN (0, 1)),
        created_at       TEXT NOT NULL
    );
    CREATE INDEX idx_uploads_sha256 ON uploads(sha256);
    """,
    # 2: graphs + immutable version history
    """
    CREATE TABLE graphs (
        id              TEXT PRIMARY KEY,
        title           TEXT NOT NULL,
        current_version INTEGER NOT NULL CHECK (current_version >= 1),
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    );
    CREATE TABLE graph_versions (
        graph_id       TEXT NOT NULL REFERENCES graphs(id) ON DELETE CASCADE,
        version        INTEGER NOT NULL CHECK (version >= 1),
        schema_version TEXT NOT NULL,
        document       TEXT NOT NULL,  -- GraphDocument JSON, validated before insert
        created_at     TEXT NOT NULL,
        PRIMARY KEY (graph_id, version)
    );
    """,
]


class GraphExistsError(Exception):
    pass


class GraphNotFoundError(Exception):
    pass


class GraphVersionConflictError(Exception):
    def __init__(self, current_version: int) -> None:
        super().__init__(f"graph is at version {current_version}")
        self.current_version = current_version


class GraphRow(BaseModel):
    id: str
    title: str
    current_version: int
    created_at: datetime
    updated_at: datetime


class GraphVersionInfo(BaseModel):
    version: int
    schema_version: str
    created_at: datetime


class GraphVersionRow(GraphVersionInfo):
    graph_id: str
    document: str


class UploadRow(BaseModel):
    id: str
    original_name: str
    kind: str
    media_type: str
    size_bytes: int
    sha256: str
    width: int | None
    height: int | None
    storage_path: str
    training_consent: bool
    created_at: datetime


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self) -> int:
        with self.connect() as conn:
            current = int(conn.execute("PRAGMA user_version").fetchone()[0])
            for version, sql in enumerate(_MIGRATIONS[current:], start=current + 1):
                conn.executescript(sql)
                conn.execute(f"PRAGMA user_version = {int(version)}")
            return len(_MIGRATIONS)

    def ping(self) -> bool:
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def insert_upload(self, row: UploadRow) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO uploads (id, original_name, kind, media_type, size_bytes, sha256,
                       width, height, storage_path, training_consent, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row.id,
                    row.original_name,
                    row.kind,
                    row.media_type,
                    row.size_bytes,
                    row.sha256,
                    row.width,
                    row.height,
                    row.storage_path,
                    int(row.training_consent),
                    row.created_at.isoformat(),
                ),
            )

    def get_upload(self, upload_id: str) -> UploadRow | None:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,)).fetchone()
        return UploadRow.model_validate(dict(r)) if r else None

    # Graphs -----------------------------------------------------------------
    def create_graph(
        self, graph_id: str, title: str, schema_version: str, document: str, now: datetime
    ) -> None:
        ts = now.isoformat()
        try:
            with self.connect() as conn:
                conn.execute(
                    "INSERT INTO graphs (id, title, current_version, created_at, updated_at)"
                    " VALUES (?, ?, 1, ?, ?)",
                    (graph_id, title, ts, ts),
                )
                conn.execute(
                    "INSERT INTO graph_versions"
                    " (graph_id, version, schema_version, document, created_at)"
                    " VALUES (?, 1, ?, ?, ?)",
                    (graph_id, schema_version, document, ts),
                )
        except sqlite3.IntegrityError as exc:
            raise GraphExistsError(graph_id) from exc

    def update_graph(
        self,
        graph_id: str,
        base_version: int,
        title: str,
        schema_version: str,
        document: str,
        now: datetime,
    ) -> int:
        """Append a new version if `base_version` is still current (optimistic concurrency)."""
        ts = now.isoformat()
        new_version = base_version + 1
        with self.connect() as conn:
            # Conditional UPDATE is atomic, so two concurrent saves can't both win.
            cur = conn.execute(
                "UPDATE graphs SET current_version = ?, title = ?, updated_at = ?"
                " WHERE id = ? AND current_version = ?",
                (new_version, title, ts, graph_id, base_version),
            )
            if cur.rowcount == 0:
                r = conn.execute(
                    "SELECT current_version FROM graphs WHERE id = ?", (graph_id,)
                ).fetchone()
                if r is None:
                    raise GraphNotFoundError(graph_id)
                raise GraphVersionConflictError(int(r["current_version"]))
            conn.execute(
                "INSERT INTO graph_versions"
                " (graph_id, version, schema_version, document, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (graph_id, new_version, schema_version, document, ts),
            )
        return new_version

    def get_graph(self, graph_id: str) -> GraphRow | None:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM graphs WHERE id = ?", (graph_id,)).fetchone()
        return GraphRow.model_validate(dict(r)) if r else None

    def list_graphs(self, limit: int = 100) -> list[GraphRow]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM graphs ORDER BY updated_at DESC, id LIMIT ?", (limit,)
            ).fetchall()
        return [GraphRow.model_validate(dict(r)) for r in rows]

    def get_graph_version(self, graph_id: str, version: int) -> GraphVersionRow | None:
        with self.connect() as conn:
            r = conn.execute(
                "SELECT * FROM graph_versions WHERE graph_id = ? AND version = ?",
                (graph_id, version),
            ).fetchone()
        return GraphVersionRow.model_validate(dict(r)) if r else None

    def list_graph_versions(self, graph_id: str) -> list[GraphVersionInfo]:
        """Version metadata only; documents are fetched individually."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT version, schema_version, created_at FROM graph_versions"
                " WHERE graph_id = ? ORDER BY version DESC",
                (graph_id,),
            ).fetchall()
        return [GraphVersionInfo.model_validate(dict(r)) for r in rows]


def utcnow() -> datetime:
    return datetime.now(UTC)

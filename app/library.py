"""Local SFX library with categories and favorites."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path.home() / "SFX Desk"
DB_NAME = "library.db"


class SfxLibrary:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or DEFAULT_ROOT
        self.lib_dir = self.root / "library"
        self.lib_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / DB_NAME
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    path TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    category TEXT NOT NULL,
                    duration REAL,
                    favorite INTEGER DEFAULT 0,
                    created_at REAL NOT NULL
                )
                """
            )

    def category_dir(self, category: str) -> Path:
        d = self.lib_dir / category
        d.mkdir(parents=True, exist_ok=True)
        return d

    def add_clip(
        self,
        src_wav: Path,
        prompt: str,
        category: str,
        duration: float | None = None,
    ) -> dict[str, Any]:
        category = (category or "misc").strip().lower()
        dest_dir = self.category_dir(category)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in category)[:24]
        filename = f"{safe}_{stamp}.wav"
        dest = dest_dir / filename
        dest.write_bytes(Path(src_wav).read_bytes())
        created = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO clips (filename, path, prompt, category, duration, favorite, created_at)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (filename, str(dest), prompt, category, duration, created),
            )
            row_id = int(cur.lastrowid)
        return self.get(row_id)

    def get(self, clip_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()
        return dict(row) if row else {}

    def list_clips(
        self,
        category: str | None = None,
        favorites_only: bool = False,
        query: str = "",
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM clips WHERE 1=1"
        args: list[Any] = []
        if category and category != "all":
            sql += " AND category=?"
            args.append(category)
        if favorites_only:
            sql += " AND favorite=1"
        if query.strip():
            sql += " AND (prompt LIKE ? OR filename LIKE ?)"
            q = f"%{query.strip()}%"
            args.extend([q, q])
        sql += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def set_favorite(self, clip_id: int, favorite: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE clips SET favorite=? WHERE id=?",
                (1 if favorite else 0, clip_id),
            )

    def delete(self, clip_id: int) -> None:
        clip = self.get(clip_id)
        if not clip:
            return
        path = Path(clip["path"])
        if path.exists():
            path.unlink()
        with self._connect() as conn:
            conn.execute("DELETE FROM clips WHERE id=?", (clip_id,))

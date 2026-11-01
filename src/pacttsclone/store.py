"""Small transactional SQLite document store; no model/audio blobs in the database."""

import json
import sqlite3
import threading
import time
from pathlib import Path


class Store:
    def __init__(self, data_dir: Path, events=None):
        self.events = events
        data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(data_dir / "pacttsclone.sqlite3", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS records "
            "(kind TEXT, id TEXT, data TEXT NOT NULL, updated REAL, "
            "PRIMARY KEY(kind,id))"
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS pending_jobs ON records "
            "(kind,json_extract(data,'$.status'),json_extract(data,'$.created_at'))"
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS channel_records ON records "
            "(kind,json_extract(data,'$.channel'),updated)"
        )
        self.db.commit()

    def put(self, kind: str, key: str, data: dict) -> dict:
        with self.lock:
            self.db.execute(
                "INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(kind,id) "
                "DO UPDATE SET data=excluded.data,updated=excluded.updated",
                (kind, key, json.dumps(data, ensure_ascii=False), time.time()),
            )
            self.db.commit()
        if self.events:
            self.events.invalidate(kind)
        return data

    def get(self, kind: str, key: str) -> dict | None:
        with self.lock:
            row = self.db.execute(
                "SELECT data FROM records WHERE kind=? AND id=?", (kind, key)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def all(self, kind: str, limit: int = 1000) -> list[dict]:
        with self.lock:
            rows = self.db.execute(
                "SELECT data FROM records WHERE kind=? ORDER BY updated DESC LIMIT ?", (kind, limit)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def pending_jobs(self):
        with self.lock:
            rows = self.db.execute(
                "SELECT data FROM records WHERE kind='job' AND "
                "json_extract(data,'$.status') IN ('queued','running') "
                "ORDER BY json_extract(data,'$.created_at') LIMIT 101"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def channel_records(self, kind, channel, limit=1000):
        with self.lock:
            rows = self.db.execute(
                "SELECT data FROM records WHERE kind=? AND json_extract(data,'$.channel')=? "
                "ORDER BY updated DESC LIMIT ?",
                (kind, channel, limit),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def patch(self, kind: str, key: str, **changes) -> dict | None:
        with self.lock:
            value = self.get(kind, key)
            if value is None:
                return None
            return self.put(kind, key, {**value, **changes})

    def delete(self, kind: str, key: str):
        with self.lock:
            self.db.execute("DELETE FROM records WHERE kind=? AND id=?", (kind, key))
            self.db.commit()
        if self.events:
            self.events.invalidate(kind)

    def close(self):
        with self.lock:
            self.db.close()

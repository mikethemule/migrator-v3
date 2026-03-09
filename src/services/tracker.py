import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from loguru import logger

from src.config import settings


class StudyStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class MigrationTracker:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS studies (
                    study_instance_uid TEXT PRIMARY KEY,
                    patient_id         TEXT,
                    study_date         TEXT,
                    study_description  TEXT,
                    accession_number   TEXT,
                    modalities         TEXT,
                    status             TEXT NOT NULL DEFAULT 'pending',
                    attempts           INTEGER NOT NULL DEFAULT 0,
                    last_error         TEXT,
                    discovered_at      TEXT NOT NULL,
                    completed_at       TEXT,
                    query_id           TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_studies_status
                ON studies(status)
            """)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def add_study(
        self,
        study_instance_uid: str,
        patient_id: str = "",
        study_date: str = "",
        study_description: str = "",
        accession_number: str = "",
        modalities: str = "",
        query_id: str = "",
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO studies
                    (study_instance_uid, patient_id, study_date, study_description,
                     accession_number, modalities, status, discovered_at, query_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    study_instance_uid,
                    patient_id,
                    study_date,
                    study_description,
                    accession_number,
                    modalities,
                    StudyStatus.PENDING,
                    now,
                    query_id,
                ),
            )

    def mark_in_progress(self, study_instance_uid: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE studies SET status = ?, attempts = attempts + 1 WHERE study_instance_uid = ?",
                (StudyStatus.IN_PROGRESS, study_instance_uid),
            )

    def mark_completed(self, study_instance_uid: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE studies SET status = ?, completed_at = ? WHERE study_instance_uid = ?",
                (StudyStatus.COMPLETED, now, study_instance_uid),
            )

    def mark_failed(self, study_instance_uid: str, error: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE studies SET status = ?, last_error = ? WHERE study_instance_uid = ?",
                (StudyStatus.FAILED, error, study_instance_uid),
            )

    def reset_failed(self):
        """Reset all failed studies back to pending for retry."""
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE studies SET status = ? WHERE status = ?",
                (StudyStatus.PENDING, StudyStatus.FAILED),
            )
            return cursor.rowcount

    def get_pending(self, limit: int | None = None) -> list[dict]:
        query = "SELECT * FROM studies WHERE status = ? ORDER BY study_date ASC"
        params: list = [StudyStatus.PENDING]
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_counts(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as count FROM studies GROUP BY status"
            ).fetchall()
            counts = {row["status"]: row["count"] for row in rows}
            total = sum(counts.values())
            counts["total"] = total
            return counts

    def is_study_known(self, study_instance_uid: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM studies WHERE study_instance_uid = ?",
                (study_instance_uid,),
            ).fetchone()
            return row is not None

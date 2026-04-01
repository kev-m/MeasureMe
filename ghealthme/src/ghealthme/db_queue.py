"""
Database definitions for the independent ghealthme job queue.
This maintains a local SQLite database (jobs.db) strictly for buffering Google Health payloads.
"""
import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "storage" / "jobs.db"

def init_db():
    """Initializes the background worker job queue for Google Health payloads."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = DB_PATH.name
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sync_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        ''')
        conn.commit()

def enqueue_job(endpoint: str, payload: dict):
    """Enqueues a webhook notification or manual trigger for background processing."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO sync_jobs (endpoint, payload) VALUES (?, ?)",
            (endpoint, json.dumps(payload))
        )
        conn.commit()

def get_pending_jobs():
    """Retrieves all pending jobs."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id, endpoint, payload FROM sync_jobs WHERE status = 'pending' ORDER BY created_at ASC")
        return cur.fetchall()

def mark_job_complete(job_id: int):
    """Marks a job as successfully processed."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            "UPDATE sync_jobs SET status = 'complete', processed_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), job_id)
        )
        conn.commit()

def mark_job_failed(job_id: int):
    """Marks a job as failed."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            "UPDATE sync_jobs SET status = 'failed', processed_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), job_id)
        )
        conn.commit()

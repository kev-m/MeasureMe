import sqlite3
import json
from datetime import datetime

QUEUE_DB_PATH = 'storage/jobs.db'

def init_queue_db(db_path=QUEUE_DB_PATH):
    """Initializes the lightweight SQLite jobs queue."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        ''')
        conn.commit()

def add_job(payload: dict, db_path=QUEUE_DB_PATH):
    """Inserts a new webhook payload into the queue."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO jobs (payload_json, status) VALUES (?, 'pending')",
            (json.dumps(payload),)
        )
        conn.commit()

def get_next_job(db_path=QUEUE_DB_PATH):
    """Fetches the oldest pending job and locks it by setting status to 'processing'."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # We use a simple select then update approach. For high concurrency, SQLite handles it,
        # but in our lightweight NAS environment, this simple polling is perfectly safe.
        cursor.execute(
            "SELECT id, payload_json FROM jobs WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
        )
        row = cursor.fetchone()
        
        if row:
            job_id = row['id']
            # Lock the job
            cursor.execute(
                "UPDATE jobs SET status = 'processing', processed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (job_id,)
            )
            conn.commit()
            return job_id, json.loads(row['payload_json'])
        return None, None

def mark_job_complete(job_id: int, db_path=QUEUE_DB_PATH):
    """Marks a job as completed."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE jobs SET status = 'completed' WHERE id = ?",
            (job_id,)
        )
        conn.commit()

def mark_job_failed(job_id: int, error_msg: str, db_path=QUEUE_DB_PATH):
    """Marks a job as failed, adding minimal error context to the payload."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE jobs SET status = 'failed', payload_json = json_insert(payload_json, '$.error', ?) WHERE id = ?",
            (error_msg, job_id)
        )
        conn.commit()

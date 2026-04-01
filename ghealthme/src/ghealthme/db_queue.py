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

def init_queue_db(jobs_path: str):
    """Initializes the lightweight SQLite jobs queue."""
    with sqlite3.connect(jobs_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        ''')
        conn.commit()

def add_job(endpoint : str, payload: dict, jobs_path: str):
    """Inserts a new webhook payload into the queue."""
    with sqlite3.connect(jobs_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO jobs (endpoint, payload_json, status) VALUES (?, ?, 'pending')",
            (endpoint, json.dumps(payload),)
        )
        conn.commit()

def get_next_job(jobs_path: str) -> tuple[int, str, dict]:
    """Fetches the oldest pending job and locks it by setting status to 'processing'."""
    with sqlite3.connect(jobs_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # We use a simple select then update approach. For high concurrency, SQLite handles it,
        # but in our lightweight NAS environment, this simple polling is perfectly safe.
        cursor.execute(
            "SELECT id, endpoint, payload_json FROM jobs WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
        )
        row = cursor.fetchone()
        
        if row:
            job_id = row['id']
            endpoint = row['endpoint,']
            # Lock the job
            cursor.execute(
                "UPDATE jobs SET status = 'processing', processed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (job_id,)
            )
            conn.commit()
            return job_id, endpoint, json.loads(row['payload_json'])
        return None, None, None

def mark_job_complete(job_id: int, jobs_path: str):
    """Marks a job as completed."""
    with sqlite3.connect(jobs_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE jobs SET status = 'completed' WHERE id = ?",
            (job_id,)
        )
        conn.commit()

def mark_job_failed(job_id: int, error_msg: str, jobs_path: str):
    """Marks a job as failed, adding minimal error context to the payload."""
    with sqlite3.connect(jobs_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE jobs SET status = 'failed', payload_json = json_insert(payload_json, '$.error', ?) WHERE id = ?",
            (error_msg, job_id)
        )
        conn.commit()

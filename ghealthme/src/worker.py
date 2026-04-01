"""
Background worker process that independently polls `jobs.db` and orchestrates data syncing.
"""
import os
import time
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

from ghealthme.db_queue import init_queue_db, get_next_job, mark_job_complete, mark_job_failed
from ghealthme.ghealth_common import load_credentials, GHealthFetcher, GHealthDataMapper
from measureme import database


logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5

def get_current_timezone(timezone_path) -> str:
    """Read the current timezone set by the web config, fallback to .env or default."""
    if os.path.exists(timezone_path):
        try:
            with open(timezone_path, "r") as f:
                tz = f.read().strip()
                if tz:
                    return tz
        except Exception as e:
            log.warning(f"Could not read timezone file: {e}")

    return os.getenv("USER_TIMEZONE", "Europe/London")

def process_job(token_path : str, endpoint : str, event_payload, data_db_path, timezone_path):
    """Processes an individual sync job dequeued from the SQLite queue."""
    
    log.info(f"Processing event payload: {event_payload}")
   
    creds = load_credentials(token_path)
    if not creds or not creds.valid:
        log.error("No valid Google credentials found. Please run the OAuth flow via the web service.")
        raise Exception("No valid Google credentials found")

        
    # Initialize MeasureMe DB session
    engine = database.get_engine(f'sqlite:///{data_db_path}')
    database.init_db(engine)
    Session = database.get_session_maker(engine)
    db_session = Session()

    # Check for a user-configured timezone override, default to Europe/London
    user_tz = get_current_timezone(timezone_path)
    # Initialize the mapper and fetcher
    mapper = GHealthDataMapper(db_session=db_session)
    fetcher = GHealthFetcher(credentials=creds, mapper=mapper)
    
    # try:
    #     # Determine the sync window: by default just sync the last 3 days to catch drift
    #     end_date = datetime.utcnow()
    #     start_date = end_date - timedelta(days=3)
        
    #     fetcher.fetch_and_process(start_date=start_date, end_date=end_date, false)
    # finally:
    #     db_session.close()

    try:
        # TODO: Examine the payload and figure out how to handle the event.
        for event in event_payload:
            collection_type = event.get('collectionType')
            date_str = event.get('date')  # Format usually YYYY-MM-DD
            fetcher.fetch_and_process(collection_type, date_str, date_str, is_webhook=True)
    finally:
        db_session.close()

def run_worker(token_path, job_db_path, data_db_path, timezone_path):
    """
    Simple background polling worker.
    Continuously loops checking the lightweight SQLite queue for new events.
    """
    log.info("Starting FitBitMe Background Worker...")
    job_id = None
    while True:
        try:
            job_id, endpoint, payload = get_next_job(jobs_path=job_db_path)

            if job_id is not None:
                log.info(f"\n[Job {job_id}] Pulled from queue.")
                # We expect payload to be an array of events from Fitbit
                # Could be multiple events in one payload, let's process the batch
                process_job(token_path, endpoint, payload, data_db_path, timezone_path)

                # If successful, mark it done.
                mark_job_complete(job_id, job_db_path)
                log.info(f"[Job {job_id}] Marked as completed.")
            else:
                # No jobs, sleep to avoid thrashing CPU
                time.sleep(2)

        except KeyboardInterrupt:
            log.info("\nWorker shutting down.")
            break
        except Exception as e:
            if 'job_id' in locals() and job_id is not None:
                log.error(f"[Job {job_id}] Failed with error: {e}")
                mark_job_failed(job_id, str(e), job_db_path)
            else:
                log.critical(f"Critical Worker Error: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    load_dotenv()

    STORAGE_DIR = os.environ.get('STORAGE_DIR', 'storage')
    GH_TOKEN_FILE = os.environ.get('GH_TOKEN_FILE', os.path.join(STORAGE_DIR, "ghealth_tokens.json"))
    MEASUREME_DB = os.environ.get('MEASUREME_DB', os.path.join(STORAGE_DIR,'measureme.db'))
    GH_JOBS_DB = os.environ.get('GH_JOBS_DB', os.path.join(STORAGE_DIR,'gh_jobs.db'))
    TZ_FILE_PATH = os.environ.get('TZ_FILE_PATH', os.path.join(STORAGE_DIR, 'timezone.txt'))

    log.info(f"Using token path: '{GH_TOKEN_FILE}'")
    log.info(f"Using Job DB path: '{GH_JOBS_DB}'")
    log.info(f"Using Data DB path: '{MEASUREME_DB}'")
    log.info(f"Using time-zone path: '{TZ_FILE_PATH}'")

    run_worker(token_path=GH_TOKEN_FILE, job_db_path=GH_JOBS_DB, data_db_path=MEASUREME_DB,
               timezone_path=TZ_FILE_PATH)

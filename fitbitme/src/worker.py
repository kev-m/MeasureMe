import time
import os
import logging

from dotenv import load_dotenv

from measureme import database
from web_services.services.queue_db import get_next_job, mark_job_complete, mark_job_failed

from fitbit_common import FitbitDataMapper, FitbitFetcher
from fitbit_client import FitbitClient

load_dotenv()

# Configure basic logging for the worker
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger('FitbitWorker')

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


def process_event(event_payload, data_db_path, timezone_path):
    """
    Handles the heavy lifting of fetching real data from Fitbit
    and persisting it to the MeasureMe database.
    """
    log.info(f"Processing event payload: {event_payload}")

    # Initialize the Fitbit client (it will auto-load stored tokens)
    try:
        client = FitbitClient()
    except Exception as e:
        log.error(f"Failed to initialize Fitbit client: {e}")
        raise e

    # Initialize MeasureMe DB session
    engine = database.get_engine(f'sqlite:///{data_db_path}')
    database.init_db(engine)
    Session = database.get_session_maker(engine)
    db_session = Session()

    # Check for a user-configured timezone override, default to Europe/London
    user_tz = get_current_timezone(timezone_path)
    mapper = FitbitDataMapper(db_session, tz_name=user_tz)
    fetcher = FitbitFetcher(client, mapper)

    try:
        # Fitbit webhooks send an array of notifications
        for event in event_payload:
            collection_type = event.get('collectionType')
            date_str = event.get('date')  # Format usually YYYY-MM-DD
            fetcher.fetch_and_process(
                collection_type, date_str, is_webhook=True)
    finally:
        db_session.close()


def run_worker(job_db_path, data_db_path, timezone_path):
    """
    Simple background polling worker.
    Continuously loops checking the lightweight SQLite queue for new events.
    """
    log.info("Starting FitBitMe Background Worker...")

    while True:
        try:
            job_id, payload = get_next_job(db_path=job_db_path)

            if job_id is not None:
                log.info(f"\n[Job {job_id}] Pulled from queue.")
                # We expect payload to be an array of events from Fitbit
                # Could be multiple events in one payload, let's process the batch
                process_event(payload, data_db_path, timezone_path)

                # If successful, mark it done.
                mark_job_complete(job_id)
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
                mark_job_failed(job_id, str(e))
            else:
                log.critical(f"Critical Worker Error: {e}")
            time.sleep(2)


if __name__ == '__main__':
    QUEUE_DB_PATH = os.environ.get('QUEUE_DB_PATH', 'storage/jobs.db')
    MEASUREME_DB = os.environ.get('MEASUREME_DB', 'storage/measureme_fb.db')
    TZ_FILE_PATH = os.environ.get('TZ_FILE_PATH', 'storage/timezone.txt')

    log.info(f"Using Job DB path: '{QUEUE_DB_PATH}'")
    log.info(f"Using Data DB path: '{MEASUREME_DB}'")
    log.info(f"Using time-zone path: '{TZ_FILE_PATH}'")

    print(f"Using DB path '{QUEUE_DB_PATH}'")
    run_worker(job_db_path=QUEUE_DB_PATH, data_db_path=MEASUREME_DB,
               timezone_path=TZ_FILE_PATH)

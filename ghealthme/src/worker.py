"""
Background worker process that independently polls `jobs.db` and orchestrates data syncing.
"""
import time
import logging
from datetime import datetime, timedelta
from ghealthme.db_queue import init_db, get_pending_jobs, mark_job_complete, mark_job_failed
from ghealthme.ghealth_common import load_credentials, GHealthFetcher, GHealthDataMapper, get_db_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5

def process_job(job):
    """Processes an individual sync job dequeued from the SQLite queue."""
    job_id = job['id']
    endpoint = job['endpoint']
    
    logger.info(f"Processing job {job_id} from {endpoint}")
    
    db_gen = get_db_session()
    db_session = next(db_gen)
    
    try:
        creds = load_credentials()
        if not creds or not creds.valid:
            logger.error("No valid Google credentials found. Please run the OAuth flow via the web service.")
            mark_job_failed(job_id)
            return

        # Initialize the mapper and fetcher
        mapper = GHealthDataMapper(db_session=db_session)
        fetcher = GHealthFetcher(credentials=creds, mapper=mapper)
        
        # Determine the sync window: by default just sync the last 3 days to catch drift
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=3)
        
        fetcher.fetch_and_process(start_date=start_date, end_date=end_date)
        
        # Mark as complete upon successful run
        mark_job_complete(job_id)
        logger.info(f"Job {job_id} successfully completed.")
        
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}", exc_info=True)
        mark_job_failed(job_id)
    finally:
        next(db_gen, None)

def main():
    logger.info("Initializing ghealthme worker queue...")
    init_db()
    
    logger.info("Worker started. Polling for pending Google Health sync jobs...")
    while True:
        try:
            jobs = get_pending_jobs()
            for job in jobs:
                process_job(job)
        except Exception as e:
            logger.error(f"Worker iteration error: {e}")
            
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()

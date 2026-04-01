"""
Standalone CLI script to manually top-up or trigger a data pull from Google Health without waiting for webhooks.
"""
import os
import sys
import argparse
import logging
from datetime import datetime, date
from pathlib import Path

from dotenv import load_dotenv
from measureme import database

load_dotenv()

STORAGE_DIR = os.environ.get('STORAGE_DIR', 'storage')
GH_TOKEN_FILE = os.environ.get('GH_TOKEN_FILE', os.path.join(STORAGE_DIR, "ghealth_tokens.json"))
MEASUREME_DB = os.environ.get('MEASUREME_DB', os.path.join(STORAGE_DIR,'measureme.db'))

print(f"Found STORAGE_DIR: {STORAGE_DIR}")
print(f"Found TOKEN_FILE: {GH_TOKEN_FILE}")
print(f"Found MEASUREME_DB: {MEASUREME_DB}")

from ghealthme.ghealth_common import load_credentials, GHealthFetcher, GHealthDataMapper

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ingest_ghealth")

def fetch_and_store_historical_data(db_url: str, start_date: date, end_date: date, only_types: list = None, tz_name: str = "Europe/London"):
    logger.info("Starting standalone Google Health API ingestion script...")
    logger.info(f"Target DB: {db_url}, Dates: {start_date} to {end_date}, Types: {only_types}, Timezone: {tz_name}")
    
    creds = load_credentials(GH_TOKEN_FILE)
    if not creds or not creds.valid:
        logger.error("No valid credentials found. Please authenticate via the ghealthme web service first.")
        sys.exit(1)

    logger.info(f"Connecting to MeasureMe DB: {db_url}")
    engine = database.get_engine(db_url)
    database.init_db(engine)
    Session = database.get_session_maker(engine)
    db_session = Session()

    try:
        mapper = GHealthDataMapper(db_session=db_session, tz_name=tz_name)
        fetcher = GHealthFetcher(credentials=creds, mapper=mapper)

        all_types = ['intraday_heart_rate', 'sleep', 'resting_heart_rate',
                    'breathing_rate', 'hrv', 'exercise', 'weight']
        types_to_run = only_types if only_types else all_types

        
        logger.info("Fetcher initialized. Syncing historical health data...")
        for collection in types_to_run:
            fetcher.fetch_and_process(collection,
                start_date=datetime.combine(start_date, datetime.min.time()),
                end_date=datetime.combine(end_date, datetime.min.time())
            ) 
        logger.info("Sync complete!")
        
    except Exception as e:
        logger.error(f"Failed to ingest Google Health data: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db_session.close()

def main():
    parser = argparse.ArgumentParser(
        description="Ingest historical data directly from Google Health API into MeasureMe.")
    parser.add_argument(
        '--db', type=str, default=f'sqlite:///{MEASUREME_DB}', help='SQLAlchemy Database URL')
    parser.add_argument('--start', type=str, required=True,
                        help='Start date YYYY-MM-DD')
    parser.add_argument('--end', type=str, required=True,
                        help='End date YYYY-MM-DD')
    parser.add_argument(
        '--types', nargs='+', help='Specify which collections to import (sleep activities). Defaults to all supported.')
    parser.add_argument('--timezone', type=str, default=None,
                        help='The IANA timezone to assume for the imported local times (e.g., Europe/London).')

    args = parser.parse_args()

    s_date = datetime.strptime(args.start, '%Y-%m-%d').date()
    e_date = datetime.strptime(args.end, '%Y-%m-%d').date()

    if s_date > e_date:
        logger.error("Start date must be before or equal to End date.")
        sys.exit(1)

    fetch_and_store_historical_data(
        args.db, s_date, e_date, args.types, args.timezone)


if __name__ == "__main__":
    main()

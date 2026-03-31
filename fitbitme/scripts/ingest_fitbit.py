import argparse
import sys
import os
import logging
from datetime import datetime, timedelta, date

from dotenv import load_dotenv

load_dotenv()

# We also need the local fitbit_client and worker logic
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from measureme import database
from fitbit_common import FitbitDataMapper, FitbitFetcher
from fitbit_client import FitbitClient

# Configure basic logging
logging.basicConfig(
    # level=logging.DEBUG,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger('FitbitIngest')


def generate_date_range(start_date: date, end_date: date):
    """Yields each date incrementally from start to end inclusive."""
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)


def fetch_and_store_historical_data(db_url: str, start: date, end: date, only_types: list = None, tz_name: str = "Europe/London"):
    """
    Fetch historical data from the Fitbit REST API and push via our Data Mapper.
    Note: Fitbit API strongly prefers fetching data day-by-day or week-by-week. We will page by day.
    """
    try:
        client = FitbitClient()
    except Exception as e:
        log.error(f"Failed to initialize Fitbit client: {e}")
        return

    log.info(f"Connecting to MeasureMe DB: {db_url}")
    engine = database.get_engine(db_url)
    database.init_db(engine)
    Session = database.get_session_maker(engine)
    db_session = Session()

    mapper = FitbitDataMapper(db_session, tz_name=tz_name)
    fetcher = FitbitFetcher(client, mapper)

    all_types = ['intraday_heart_rate', 'sleep', 'resting_heart_rate',
                 'breathing_rate', 'hrv', 'exercises', 'weight']
    types_to_run = only_types if only_types else all_types

    try:
        for current_date in generate_date_range(start, end):
            date_str = current_date.strftime('%Y-%m-%d')
            log.info(f"--- Fetching API data for {date_str} ---")

            # We use our newly extracted single source of truth in FitbitFetcher
            for collection in types_to_run:
                try:
                    fetcher.fetch_and_process(collection, date_str)
                except Exception as e:
                    # Specific error already logged by fetcher, we pass to next
                    pass

            # Be polite to the Fitbit API Rate limits (150 requests per hour!)
            time.sleep(1)

        log.info("Historical ingest complete.")

    finally:
        db_session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest historical data directly from Fitbit REST API into MeasureMe.")
    parser.add_argument(
        '--db', type=str, default='sqlite:///storage/measureme_fb.db', help='SQLAlchemy Database URL')
    parser.add_argument('--start', type=str, required=True,
                        help='Start date YYYY-MM-DD')
    parser.add_argument('--end', type=str, required=True,
                        help='End date YYYY-MM-DD')
    parser.add_argument(
        '--types', nargs='+', help='Specify which collections to import (sleep activities). Defaults to all supported.')
    parser.add_argument('--timezone', type=str, default="Europe/London",
                        help='The IANA timezone to assume for the imported local times (e.g., Europe/London).')

    args = parser.parse_args()
    import time

    s_date = datetime.strptime(args.start, '%Y-%m-%d').date()
    e_date = datetime.strptime(args.end, '%Y-%m-%d').date()

    if s_date > e_date:
        log.error("Start date must be before or equal to End date.")
        sys.exit(1)

    fetch_and_store_historical_data(
        args.db, s_date, e_date, args.types, args.timezone)

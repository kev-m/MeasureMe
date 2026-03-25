"""
Example: Unified Abstraction Query
==================================
This script demonstrates how to connect to the MeasureMe database
and execute simple discovery and extraction queries using the new
high-level `MeasureMeQuery` abstraction.
"""

import os
import sys
from datetime import datetime

# Ensure the measureme src directory is in the Python path
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(base_dir, 'src'))

from measureme.database import get_engine, get_session_maker
from measureme.query import MeasureMeQuery

def main():
    """Execute generic queries against the MeasureMe database without raw SQLAlchemy."""

    db_path = os.path.join(base_dir, 'measureme.db')
    db_url = f"sqlite:///{db_path}"

    print(f"Connecting to MeasureMe DB: {db_url}")

    engine = get_engine(db_url)
    Session = get_session_maker(engine)

    with Session() as session:
        # Initialize the abstraction interface
        mq = MeasureMeQuery(session)

        print("\n--- Introspection: What is in this database? ---")
        st = mq.get_available_session_types()
        mt = mq.get_available_metric_types()
        it = mq.get_available_intraday_types()
        bounds = mq.get_date_bounds()
        
        print(f"Session Types Found: {st}")
        print(f"Metric Types Found: {mt}")
        print(f"Intraday Telemetry Types Found: {it}")
        print(f"Data Bound Scope: {bounds['first_record']} TO {bounds['last_record']}")

        print("\n--- Safely Extracting Data ---")
        if bounds['last_record'] and 'sleep_main' in st:
            # Attempt to pull sleep for the last valid year of data in the DB
            start_date = bounds['last_record'].replace(year=bounds['last_record'].year - 1)
            end_date = bounds['last_record']
            
            recent_sleep = mq.get_sessions(
                session_type='sleep', 
                start_date=start_date, 
                end_date=end_date, 
                limit=5
            )
            
            for sleep in recent_sleep:
                duration_hrs = sleep.duration_seconds / 3600.0 if sleep.duration_seconds else 0
                print(f"Sleep Date: {sleep.start_time.date()}, Duration: {duration_hrs:.2f} hours")
        else:
            print("No Sleep data or bounds available in the database to query.")
            
        if bounds['last_record'] and 'resting_heart_rate' in mt:
            start_date = bounds['last_record'].replace(year=bounds['last_record'].year - 1)
            end_date = bounds['last_record']
            
            recent_rhr = mq.get_daily_metrics(
                metric_type='resting_heart_rate',
                start_date=start_date,
                end_date=end_date
            )
            
            print(f"Total RHR entries available for trailing year: {len(recent_rhr)}")
            

if __name__ == "__main__":
    main()
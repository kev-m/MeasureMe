"""
Example: Basic Query
====================
This script demonstrates how to connect to the MeasureMe database
using explicit SQLAlchemy models and execute simple queries to 
retrieve recently imported health metrics and sessions.
"""

import os
import sys

# Ensure the measureme src directory is in the Python path
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(base_dir, 'src'))

from measureme.database import get_engine, get_session_maker
from measureme.models import HealthMetric, HealthSession

def main():
    """Execute basic queries against the MeasureMe database."""
    
    # Locate the SQLite database created by ingest_fitout.py
    db_path = os.path.join(base_dir, 'measureme_dev.db')
    db_url = f"sqlite:///{db_path}"
    
    print(f"Connecting to MeasureMe DB: {db_url}")
    
    engine = get_engine(db_url)
    Session = get_session_maker(engine)

    with Session() as session:
        # 1. Query the 5 most recent sleep sessions
        print("\n--- Recent Sleep Sessions ---")
        recent_sleep = session.query(HealthSession)\
            .filter(HealthSession.session_type == 'sleep')\
            .order_by(HealthSession.start_time.desc())\
            .limit(5).all()
            
        if not recent_sleep:
            print("No sleep data found.")
        for sleep in recent_sleep:
            duration_hrs = sleep.duration_seconds / 3600.0 if sleep.duration_seconds else 0
            print(f"Date: {sleep.start_time.date()}, Duration: {duration_hrs:.2f} hours")

        # 2. Query the 5 most recent weight metrics
        print("\n--- Recent Weight Metrics ---")
        recent_weights = session.query(HealthMetric)\
            .filter(HealthMetric.metric_type == 'weight')\
            .order_by(HealthMetric.timestamp.desc())\
            .limit(5).all()
            
        if not recent_weights:
            print("No weight data found.")
        for w in recent_weights:
            print(f"Date: {w.timestamp.date()}, Weight: {w.value} {w.unit}")

        # 3. Query the 5 most recent exercises
        print("\n--- Recent Exercises ---")
        recent_exercises = session.query(HealthSession)\
            .filter(HealthSession.session_type == 'exercise')\
            .order_by(HealthSession.start_time.desc())\
            .limit(5).all()
            
        if not recent_exercises:
            print("No exercise data found.")
        for ex in recent_exercises:
            meta = ex.get_metadata()
            name = meta.get('activity_name', 'Unknown')
            cals = meta.get('calories', 'N/A')
            print(f"Date: {ex.start_time.date()}, Activity: '{name}', Calories: {cals} kcal, Duration: {ex.duration_seconds // 60} mins")

if __name__ == "__main__":
    main()

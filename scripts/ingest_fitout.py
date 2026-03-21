import argparse
import sys
import json
from datetime import datetime, date

import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from measureme.database import get_engine, init_db, get_session_maker
from measureme.models import HealthSession, HealthMetric, HealthIntraday

try:
    import fitout as fo
except ImportError:
    print("WARNING: fitout is not installed in the current pip environment.", file=sys.stderr)
    print("Please install it (e.g., pip install -e ../FitOut) to proceed.", file=sys.stderr)
    sys.exit(1)

def dt_from_iso(iso_str):
    if not iso_str:
        return None
    try:
        # e.g., '2024-07-21T23:30:00.000'
        return datetime.strptime(iso_str, '%Y-%m-%dT%H:%M:%S.%f')
    except ValueError:
        # e.g., '2024-07-21T23:30:00'
        return datetime.strptime(iso_str, '%Y-%m-%dT%H:%M:%S')

def process_export(path: str, db_url: str, start: date, end: date, only_types: list = None, user_id: int = 1):
    """
    Process a FitOut directory and insert data into MeasureMe database.
    """
    engine = get_engine(db_url)
    init_db(engine)
    Session = get_session_maker(engine)
    
    print(f"Connecting to MeasureMe DB: {db_url}")
    print(f"Reading Fitbit Takeout data from ZIP: {path} ({start} to {end}) for User ID: {user_id}")
    
    # We use ZipFileLoader since fitout can handle Google Takeout zips directly
    data_source = fo.ZipFileLoader(path)
    FITBIT_SOURCE_ID = 1
    
    # Define available imports map
    all_types = ['sleep', 'resting_heart_rate', 'breathing_rate', 'hrv', 'intraday_heart_rate', 'exercises', 'weight']
    types_to_run = only_types if only_types else all_types

    with Session() as session:
        if 'sleep' in types_to_run:
            print("Importing Sleep...")
            sleep_importer = fo.BasicSleepInfo(data_source)
            try:
                # Using get_raw_sessions to intentionally capture naps and distinct biphasic sleep blocks
                sleep_data_raw = sleep_importer.get_raw_sessions(start, end)
                
                for sleep_entry in sleep_data_raw:
                    if sleep_entry.get('startTime') and sleep_entry.get('endTime'):
                        db_start = dt_from_iso(sleep_entry['startTime'])
                        db_end = dt_from_iso(sleep_entry['endTime'])
                        mins_awake = sleep_entry.get('minutesAwake', 0)
                        is_main_sleep = sleep_entry.get('mainSleep', True)
                        duration_s = int((db_end - db_start).total_seconds()) if db_start and db_end else 0
                        
                        hs = HealthSession(
                            user_id=user_id,
                            source_id=FITBIT_SOURCE_ID,
                            session_type='sleep',
                            start_time=db_start,
                            end_time=db_end,
                            duration_seconds=duration_s,
                            metadata_json=json.dumps({
                                "minutes_awake": mins_awake,
                                "main_sleep": is_main_sleep,
                                "efficiency": sleep_entry.get('efficiency'),
                                "time_in_bed": sleep_entry.get('timeInBed')
                            })
                        )
                        
                        existing = session.query(HealthSession).filter_by(
                            user_id=user_id,
                            session_type='sleep',
                            start_time=db_start
                        ).first()
                        
                        if not existing:
                            session.add(hs)
                        else:
                            existing.end_time = hs.end_time
                            existing.duration_seconds = hs.duration_seconds
                            existing.metadata_json = hs.metadata_json
            except Exception as e:
                print(f"Warning: Failed to import Sleep data: {e}")

        def insert_daily_metrics(importer, metric_type, unit):
            try:
                values = importer.get_data(start, end)
                dates = getattr(importer, 'dates', [])
                for d, val in zip(dates, values):
                    if val is not None and d is not None:
                        dt = datetime.combine(d, datetime.min.time())
                        
                        existing = session.query(HealthMetric).filter_by(
                            user_id=user_id,
                            metric_type=metric_type,
                            timestamp=dt
                        ).first()
                        
                        if not existing:
                            m = HealthMetric(
                                user_id=user_id,
                                source_id=FITBIT_SOURCE_ID,
                                metric_type=metric_type,
                                value=val,
                                unit=unit,
                                timestamp=dt
                            )
                            session.add(m)
                        else:
                            existing.value = val
                            existing.unit = unit
            except Exception as e:
                print(f"Warning: Failed to import {metric_type}: {e}")

        if 'resting_heart_rate' in types_to_run:
            print("Importing Resting Heart Rate...")
            try:
                insert_daily_metrics(fo.RestingHeartRate(data_source), 'resting_heart_rate', 'bpm')
            except AttributeError:
                 print("Warning: RestingHeartRate not found in fitout")

        if 'breathing_rate' in types_to_run:
            print("Importing Breathing Rate...")
            try:
                insert_daily_metrics(fo.BreathingRate(data_source), 'breathing_rate', 'breaths/min')
            except AttributeError:
                print("Warning: BreathingRate not found in fitout")

        if 'hrv' in types_to_run:
            print("Importing Heart Rate Variability...")
            try:
                insert_daily_metrics(fo.HeartRateVariability(data_source), 'hrv_rmssd', 'ms')
            except AttributeError:
                print("Warning: HeartRateVariability not found in fitout")
            except Exception as e:
                print(f"Warning: Failed to import HRV: {e}")
            
        if 'intraday_heart_rate' in types_to_run:
            print("Importing Intraday Heart Rate...")
            try:
                # Note: BasicHeartRate requires datetime bounds rather than just dates
                bhr_importer = fo.BasicHeartRate(data_source)
                # Fetch at 60s interval resolution as an example
                bhr_importer.set_sampling_interval(60) 
                # Provide exact datetimes
                s_dt = datetime.combine(start, datetime.min.time())
                e_dt = datetime.combine(end, datetime.max.time())
                print(f"Fetching Heart Rate telemetry between {s_dt} and {e_dt} - this may take a while")
                
                bhr_values = bhr_importer.get_data(s_dt, e_dt)
                bhr_dates = getattr(bhr_importer, 'dates', [])
                
                # 1 maps to generic 'heart_rate' in our theoretical telemetry types
                HEART_RATE_METRIC_TYPE_ID = 1 
                for t, val in zip(bhr_dates, bhr_values):
                    if val is not None and t is not None:
                        hi = HealthIntraday(
                            timestamp_utc=int(t.timestamp()),
                            user_id=user_id,
                            metric_type_id=HEART_RATE_METRIC_TYPE_ID,
                            value=val
                        )
                        session.merge(hi)  # Merge handles composite PK conflicts
            except AttributeError:
                print("Warning: BasicHeartRate not found in fitout")
            except Exception as e:
                print(f"Warning: Failed to import Intraday Heart Rate: {e}")
            
        if 'exercises' in types_to_run:
            print("Importing Exercises...")
            try:
                # We need timedelta here, verify it's imported at the top. Let's use `from datetime import datetime, date, timedelta` if not, or add timedelta if it's missing. I'll check imports later.
                from datetime import timedelta
                
                exercise_importer = fo.ExerciseInfo(data_source)
                exercise_data_raw = exercise_importer.get_raw_sessions(start, end)
                
                for ex in exercise_data_raw:
                    dt_start = None
                    try:
                        dt_start = datetime.fromisoformat(ex.get('startTimeIso'))
                    except (ValueError, TypeError):
                        continue
                        
                    duration_s = ex.get('duration', 0) // 1000  # Fitbit provides milliseconds
                    dt_end = dt_start + timedelta(seconds=duration_s)
                    
                    metadata = {
                        "activity_name": ex.get('activityName'),
                        "calories": ex.get('calories'),
                        "steps": ex.get('steps'),
                        "average_heart_rate": ex.get('averageHeartRate'),
                        "log_id": ex.get('logId')
                    }
                    
                    # Remove None values from metadata
                    metadata = {k: v for k, v in metadata.items() if v is not None}
                    
                    hs = HealthSession(
                        user_id=user_id,
                        source_id=FITBIT_SOURCE_ID,
                        session_type='exercise',
                        start_time=dt_start,
                        end_time=dt_end,
                        duration_seconds=duration_s,
                        metadata_json=json.dumps(metadata)
                    )
                    
                    existing = session.query(HealthSession).filter_by(
                        user_id=user_id,
                        session_type='exercise',
                        start_time=dt_start
                    ).first()
                    
                    if not existing:
                        session.add(hs)
                    else:
                        existing.end_time = hs.end_time
                        existing.duration_seconds = hs.duration_seconds
                        existing.metadata_json = hs.metadata_json
                        
            except AttributeError:
                print("Warning: ExerciseInfo not found in fitout")
            except Exception as e:
                print(f"Warning: Failed to import Exercises: {e}")

        if 'weight' in types_to_run:
            print("Importing Weight...")
            try:
                weight_importer = fo.WeightInfo(data_source)
                weight_data_raw = weight_importer.get_raw_sessions(start, end)
                
                for w_entry in weight_data_raw:
                    dt = None
                    try:
                        dt = datetime.fromisoformat(w_entry.get('startTimeIso'))
                    except (ValueError, TypeError):
                        continue
                        
                    # Insert weight
                    if w_entry.get('weight') is not None:
                        existing = session.query(HealthMetric).filter_by(
                            user_id=user_id,
                            metric_type='weight',
                            timestamp=dt
                        ).first()
                        
                        if not existing:
                            m = HealthMetric(
                                user_id=user_id,
                                source_id=FITBIT_SOURCE_ID,
                                metric_type='weight',
                                value=w_entry.get('weight'),
                                unit='kg', # or lbs, depending on user export format. Assuming numerical standard.
                                timestamp=dt
                            )
                            session.add(m)
                        else:
                            existing.value = w_entry.get('weight')

                    # Insert bmi
                    if w_entry.get('bmi') is not None:
                        existing_bmi = session.query(HealthMetric).filter_by(
                            user_id=user_id,
                            metric_type='bmi',
                            timestamp=dt
                        ).first()
                        
                        if not existing_bmi:
                            m = HealthMetric(
                                user_id=user_id,
                                source_id=FITBIT_SOURCE_ID,
                                metric_type='bmi',
                                value=w_entry.get('bmi'),
                                unit='index',
                                timestamp=dt
                            )
                            session.add(m)
                        else:
                            existing_bmi.value = w_entry.get('bmi')

                    # Insert fat
                    if w_entry.get('fat') is not None:
                        existing_fat = session.query(HealthMetric).filter_by(
                            user_id=user_id,
                            metric_type='body_fat',
                            timestamp=dt
                        ).first()
                        
                        if not existing_fat:
                            m = HealthMetric(
                                user_id=user_id,
                                source_id=FITBIT_SOURCE_ID,
                                metric_type='body_fat',
                                value=w_entry.get('fat'),
                                unit='percent',
                                timestamp=dt
                            )
                            session.add(m)
                        else:
                            existing_fat.value = w_entry.get('fat')

            except AttributeError:
                print("Warning: WeightInfo not found in fitout")
            except Exception as e:
                print(f"Warning: Failed to import Weight: {e}")
        
        try:
            session.commit()
            print("Data ingestion complete!")
        except Exception as e:
            session.rollback()
            print(f"Error during database commit: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest FitOut unzipped data into MeasureMe database.")
    parser.add_argument('path', type=str, help='Path to the unzipped Google/Fitbit Export directory')
    parser.add_argument('--db', type=str, default='sqlite:///measureme_dev.db', help='SQLAlchemy Database URL')
    parser.add_argument('--start', type=str, required=True, help='Start date YYYY-MM-DD')
    parser.add_argument('--end', type=str, required=True, help='End date YYYY-MM-DD')
    parser.add_argument('--types', nargs='+', help='Specify which health types to import (e.g. sleep exercises resting_heart_rate). Defaults to all.')
    parser.add_argument('--user-id', type=int, default=1, help='User ID to associate with the imported data. Defaults to 1.')
    
    args = parser.parse_args()
    
    s_date = datetime.strptime(args.start, '%Y-%m-%d').date()
    e_date = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    process_export(args.path, args.db, s_date, e_date, args.types, args.user_id)

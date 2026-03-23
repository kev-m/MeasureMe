import argparse
import sys
import json
import csv
import zoneinfo
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

DESTINATION_TZ_MAP = {
    "UK": "Europe/London",
    "Italy": "Europe/Rome",
    "Norway": "Europe/Oslo",
    "Netherlands": "Europe/Amsterdam",
    "Spain (France, Italy)": "Europe/Madrid",
    "Spain (Mallorca)": "Europe/Madrid",
    "Spain": "Europe/Madrid",
    "Canada": "America/Toronto",
    "France": "Europe/Paris",
}

def parse_holidays_csv(csv_path: str):
    holidays = []
    if not csv_path or not os.path.exists(csv_path):
        return holidays
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            sample = f.read(1024)
            f.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters='\t,;')
            reader = csv.DictReader(f, dialect=dialect)
            for row in reader:
                try:
                    start_dt = datetime.strptime(row['Departure Date'].strip(), '%Y/%m/%d').date()
                    end_dt = datetime.strptime(row['Return Date'].strip(), '%Y/%m/%d').date()
                    dest = row['Destination'].strip()
                    holidays.append({
                        'start': start_dt,
                        'end': end_dt,
                        'destination': dest
                    })
                except Exception as e:
                    print(f"Skipping holiday row {row}: {e}")
    except Exception as e:
        print(f"Warning: Could not parse holidays CSV: {e}")
        
    return holidays

def get_timezone_for_date(dt_date, holidays, default_tz="Europe/London"):
    if not dt_date:
        return default_tz
    for h in holidays:
        if h['start'] <= dt_date <= h['end']:
            return DESTINATION_TZ_MAP.get(h['destination'], default_tz)
    return default_tz

def convert_utc_to_local(utc_naive_dt, tz_name):
    if not utc_naive_dt:
        return None, tz_name
    try:
        utc_aware = utc_naive_dt.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
        local_aware = utc_aware.astimezone(zoneinfo.ZoneInfo(tz_name))
        return local_aware.replace(tzinfo=None), tz_name
    except zoneinfo.ZoneInfoNotFoundError:
        return utc_naive_dt, tz_name

def dt_from_iso(iso_str):
    if not iso_str:
        return None
    try:
        # e.g., '2024-07-21T23:30:00.000'
        return datetime.strptime(iso_str, '%Y-%m-%dT%H:%M:%S.%f')
    except ValueError:
        # e.g., '2024-07-21T23:30:00'
        return datetime.strptime(iso_str, '%Y-%m-%dT%H:%M:%S')

def process_export(path: str, db_url: str, start: date, end: date, only_types: list = None, user_id: int = 1, holidays_csv: str = None, default_tz: str = "Europe/London", weight_to_kgs: bool = False):
    """
    Process a FitOut directory and insert data into MeasureMe database.
    """
    engine = get_engine(db_url)
    init_db(engine)
    Session = get_session_maker(engine)
    
    print(f"Connecting to MeasureMe DB: {db_url}")
    print(f"Reading Fitbit Takeout data from ZIP: {path} ({start} to {end}) for User ID: {user_id}")
    
    holidays = parse_holidays_csv(holidays_csv) if holidays_csv else []
    
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
                        db_start = datetime.fromisoformat(sleep_entry['startTime'])
                        db_end = datetime.fromisoformat(sleep_entry['endTime'])

                        # Google TakeOut exports weight timestamps as Naive Local Time (disguised without a Z). 
                        # We should NOT shift it by UTC offsets, just format it naively as-is.
                        db_start = db_start.replace(tzinfo=None)
                        tz_name = get_timezone_for_date(db_start.date() if db_start else None, holidays, default_tz)
                        db_end = db_end.replace(tzinfo=None)
                        tz_used = tz_name
                        
                        # FITBIT API SEMANTICS: Sleep is assigned to the date when you wake up (the end time).
                        # If the sleep ended on a day outside our bounds, discard it.
                        if not (start <= db_end.date() <= end):
                            continue
                        
                        mins_awake = sleep_entry.get('minutesAwake', 0)
                        is_main_sleep = sleep_entry.get('mainSleep', True)
                        duration_s = int((db_end - db_start).total_seconds()) if db_start and db_end else 0

                        # FitBit API, all sleep is sleep_main!?
                        sleep_type = 'sleep_main' # if is_main_sleep else 'sleep'
                        
                        hs = HealthSession(
                            user_id=user_id,
                            source_id=FITBIT_SOURCE_ID,
                            session_type=sleep_type,
                            start_time=db_start,
                            end_time=db_end,
                            duration_seconds=duration_s,
                            timezone=tz_used,
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
                            existing.timezone = hs.timezone
                            existing.metadata_json = hs.metadata_json
            except Exception as e:
                print(f"Warning: Failed to import Sleep data: {e}")

        def insert_daily_metrics(importer, metric_type, unit):
            try:
                values = importer.get_data(start, end)
                dates = getattr(importer, 'dates', [])
                for d, val in zip(dates, values):
                    if val is not None and d is not None:
                        # For daily metrics, it's already a date, so applying tz offset at midnight is less relevant,
                        # but we still record the timezone context explicitly.
                        tz_name = get_timezone_for_date(d, holidays, default_tz)
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
                                timestamp=dt,
                                timezone=tz_name
                            )
                            session.add(m)
                        else:
                            existing.value = val
                            existing.unit = unit
                            existing.timezone = tz_name
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
                # Provide exact datetimes mapped dynamically from Local bounds to UTC bounds
                s_tz = get_timezone_for_date(start, holidays, default_tz)
                e_tz = get_timezone_for_date(end, holidays, default_tz)
                
                s_dt_local = datetime.combine(start, datetime.min.time(), tzinfo=zoneinfo.ZoneInfo(s_tz))
                e_dt_local = datetime.combine(end, datetime.max.time(), tzinfo=zoneinfo.ZoneInfo(e_tz))
                
                # fitout queries Google's Takeout which is structured exactly in UTC. 
                s_dt_utc = s_dt_local.astimezone(zoneinfo.ZoneInfo("UTC")).replace(tzinfo=None)
                e_dt_utc = e_dt_local.astimezone(zoneinfo.ZoneInfo("UTC")).replace(tzinfo=None)
                
                print(f"Fetching Heart Rate telemetry between local {s_dt_local} and {e_dt_local}")
                print(f"-> Mapped to absolute UTC bounds: {s_dt_utc} and {e_dt_utc}")
                
                bhr_values = bhr_importer.get_data(s_dt_utc, e_dt_utc)
                bhr_dates = getattr(bhr_importer, 'dates', [])
                
                # 1 maps to generic 'heart_rate' in our theoretical telemetry types
                HEART_RATE_METRIC_TYPE_ID = 1 
                for t, val in zip(bhr_dates, bhr_values):
                    if val is not None and t is not None:
                        # Google Takeout returns strictly UTC datetimes, but fitout may return them as naive datetimes.
                        # Always coerce them to be explicitly UTC so .timestamp() computes absolute epoch correctly.
                        if t.tzinfo is None:
                            t = t.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
                        
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
                    dt_start_utc = None
                    try:
                        dt_start_utc = datetime.fromisoformat(ex.get('startTimeIso'))
                    except (ValueError, TypeError):
                        continue
                        
                    tz_name = get_timezone_for_date(dt_start_utc.date() if dt_start_utc else None, holidays, default_tz)
                    dt_start, tz_used = convert_utc_to_local(dt_start_utc, tz_name)
                    
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
                        timezone=tz_used,
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
                        existing.timezone = hs.timezone
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
                    dt_utc = None
                    try:
                        dt_utc = datetime.fromisoformat(w_entry.get('startTimeIso'))
                    except (ValueError, TypeError):
                        continue
                        
                    # Google TakeOut exports weight timestamps as Naive Local Time (disguised without a Z). 
                    # We should NOT shift it by UTC offsets, just format it naively as-is.
                    dt = dt_utc.replace(tzinfo=None)
                    tz_name = get_timezone_for_date(dt.date() if dt else None, holidays, default_tz)
                    tz_used = tz_name
                        
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
                                timestamp=dt,
                                timezone=tz_used
                            )
                            session.add(m)
                        else:
                            existing.value = w_entry.get('weight')
                            existing.timezone = tz_used

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
                                timestamp=dt,
                                timezone=tz_used
                            )
                            session.add(m)
                        else:
                            existing_bmi.value = w_entry.get('bmi')
                            existing_bmi.timezone = tz_used

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
                                timestamp=dt,
                                timezone=tz_used
                            )
                            session.add(m)
                        else:
                            existing_fat.value = w_entry.get('fat')
                            existing_fat.timezone = tz_used

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
    parser.add_argument('--holidays-csv', type=str, help='Path to a CSV file containing holiday dates to calculate proper timezones.')
    parser.add_argument('--timezone', type=str, default='Europe/London', help='The default IANA timezone to use (e.g. Europe/London).')
    
    args = parser.parse_args()
    
    s_date = datetime.strptime(args.start, '%Y-%m-%d').date()
    e_date = datetime.strptime(args.end, '%Y-%m-%d').date()
    
    process_export(args.path, args.db, s_date, e_date, args.types, args.user_id, args.holidays_csv)

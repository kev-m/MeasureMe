from measureme.models import HealthMetric, HealthIntraday, SleepSession, ExerciseSession, MetricTypeFromString
from measureme.database import get_engine, init_db, get_session_maker
import argparse
import sys
import json
import csv
import zoneinfo
from datetime import datetime, date

import os
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../src')))

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
                    start_dt = datetime.strptime(
                        row['Departure Date'].strip(), '%Y/%m/%d').date()
                    end_dt = datetime.strptime(
                        row['Return Date'].strip(), '%Y/%m/%d').date()
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
            dest = h['destination']
            # Support explicit valid IANA timezones (e.g. "Asia/Tokyo")
            try:
                zoneinfo.ZoneInfo(dest)
                return dest
            except zoneinfo.ZoneInfoNotFoundError:
                pass

            # Extract main country name before any parenthesis (e.g. "Spain (Mallorca)" -> "Spain")
            base_dest = dest.split('(')[0].strip()

            return DESTINATION_TZ_MAP.get(base_dest, default_tz)
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
    print(
        f"Reading Fitbit Takeout data from ZIP: {path} ({start} to {end}) for User ID: {user_id}")

    holidays = parse_holidays_csv(holidays_csv) if holidays_csv else []

    # We use ZipFileLoader since fitout can handle Google Takeout zips directly
    data_source = fo.ZipFileLoader(path)
    FITBIT_SOURCE_ID = 1

    # Define available imports map
    all_types = ['sleep', 'resting_heart_rate', 'breathing_rate',
                 'hrv', 'intraday_heart_rate', 'exercises', 'weight']
    types_to_run = only_types if only_types else all_types

    with Session() as session:
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

                s_dt_local = datetime.combine(
                    start, datetime.min.time(), tzinfo=zoneinfo.ZoneInfo(s_tz))
                e_dt_local = datetime.combine(
                    end, datetime.max.time(), tzinfo=zoneinfo.ZoneInfo(e_tz))

                # fitout queries Google's Takeout which is structured exactly in UTC.
                s_dt_utc = s_dt_local.astimezone(
                    zoneinfo.ZoneInfo("UTC")).replace(tzinfo=None)
                e_dt_utc = e_dt_local.astimezone(
                    zoneinfo.ZoneInfo("UTC")).replace(tzinfo=None)

                print(
                    f"Fetching Heart Rate telemetry between local {s_dt_local} and {e_dt_local}")
                print(
                    f"-> Mapped to absolute UTC bounds: {s_dt_utc} and {e_dt_utc}")

                bhr_values = bhr_importer.get_data(s_dt_utc, e_dt_utc)
                bhr_dates = getattr(bhr_importer, 'dates', [])
               
                # OPTIMIZATION: Query all existing PKs for the range first
                min_ts = int(s_dt_utc.replace(tzinfo=zoneinfo.ZoneInfo("UTC")).timestamp())
                max_ts = int(e_dt_utc.replace(tzinfo=zoneinfo.ZoneInfo("UTC")).timestamp())

                # Extract heart_rate_id using the key 'heart_rate'
                heart_rate_id = MetricTypeFromString('heart_rate')
                
                existing_pks = set(
                    row[0] for row in session.query(HealthIntraday.timestamp_utc).filter(
                        HealthIntraday.user_id == user_id,
                        HealthIntraday.metric_type_id == heart_rate_id,
                        HealthIntraday.timestamp_utc >= min_ts,
                        HealthIntraday.timestamp_utc <= max_ts
                    ).all()
                )
                
                new_mappings = []
                for t, val in zip(bhr_dates, bhr_values):
                    if val is not None and t is not None:
                        # Google Takeout returns strictly UTC datetimes, but fitout may return them as naive datetimes.
                        # Always coerce them to be explicitly UTC so .timestamp() computes absolute epoch correctly.
                        if t.tzinfo is None:
                            t = t.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
                        
                        ts_val = int(t.timestamp())
                        
                        if ts_val not in existing_pks:
                            new_mappings.append({
                                'timestamp_utc': ts_val,
                                'user_id': user_id,
                                'metric_type_id': heart_rate_id,
                                'value': val
                            })
                            
                if new_mappings:
                    # bulk_insert_mappings is dramatically faster than individual add() or merge() calls 
                    # and skips SQLAlchemy tracking overhead.
                    session.bulk_insert_mappings(HealthIntraday, new_mappings)
                    
            except AttributeError:
                print("Warning: BasicHeartRate not found in fitout")
            except Exception as e:
                print(f"Warning: Failed to import Intraday Heart Rate: {e}")

        if 'sleep' in types_to_run:
            print("Importing Sleep...")
            sleep_importer = fo.BasicSleepInfo(data_source)
            try:
                # Using get_raw_sessions to intentionally capture naps and distinct biphasic sleep blocks
                sleep_data_raw = sleep_importer.get_raw_sessions(start, end)

                for sleep_entry in sleep_data_raw:
                    if sleep_entry.get('startTime') and sleep_entry.get('endTime'):
                        db_start = datetime.fromisoformat(
                            sleep_entry['startTime'])
                        db_end = datetime.fromisoformat(sleep_entry['endTime'])

                        # Google TakeOut exports sleep timestamps as Naive Local Time (disguised without a Z).
                        # We should NOT shift it by UTC offsets, just format it naively as-is.
                        db_start = db_start.replace(tzinfo=None)
                        tz_name = get_timezone_for_date(
                            db_start.date() if db_start else None, holidays, default_tz)
                        db_end = db_end.replace(tzinfo=None)
                        tz_used = tz_name

                        # FITBIT API SEMANTICS: Sleep is assigned to the date when you wake up (the end time).
                        # If the sleep ended on a day outside our bounds, discard it.
                        if not (start <= db_end.date() <= end):
                            continue

                        mins_awake = sleep_entry.get('minutesAwake', 0)
                        is_main_sleep = sleep_entry.get('mainSleep', True)
                        duration_s = sleep_entry.get('minutesAsleep', 0) * 60

                        # It is safe to cast to int, as Google TakeOut logId is a number
                        log_id = int(sleep_entry.get('logId')
                                     ) if sleep_entry.get('logId') else None

                        
                        summary = sleep_entry.get('levels', {}).get('summary', {})
                        if not summary and hasattr(sleep_entry, 'get'):
                            # Fallback if fitout already flattened it
                            summary = sleep_entry
                        
                        # Delete levels.data and levels.shortData
                        if 'levels' in sleep_entry:
                            sleep_entry['levels'].pop('data', None)
                            sleep_entry['levels'].pop('shortData', None)

                        hs = SleepSession(
                            global_id=log_id,
                            user_id=user_id,
                            source_id=FITBIT_SOURCE_ID,
                            start_time=db_start,
                            end_time=db_end,
                            duration_seconds=duration_s,
                            timezone=tz_used,
                            metadata_json=json.dumps(sleep_entry),
                            is_main_sleep=is_main_sleep,
                            efficiency_score=sleep_entry.get('efficiency', 0),
                            deep_sleep_seconds=summary.get('deep', {}).get('minutes', summary.get('summary_deep_mins', 0)) * 60,
                            light_sleep_seconds=summary.get('light', {}).get('minutes', summary.get('summary_light_mins', 0)) * 60,
                            rem_sleep_seconds=summary.get('rem', {}).get('minutes', summary.get('summary_rem_mins', 0)) * 60,
                            awake_seconds=summary.get('wake', {}).get('minutes', summary.get('summary_wake_mins', mins_awake)) * 60,
                            time_in_bed_seconds=sleep_entry.get('timeInBed', 0) * 60
                        )

                        if log_id:
                            existing = session.query(SleepSession).filter_by(
                                global_id=log_id).first()
                        else:
                            existing = session.query(SleepSession).filter_by(
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
                            existing.is_main_sleep = hs.is_main_sleep
                            existing.efficiency_score = hs.efficiency_score
                            existing.deep_sleep_seconds = hs.deep_sleep_seconds
                            existing.light_sleep_seconds = hs.light_sleep_seconds
                            existing.rem_sleep_seconds = hs.rem_sleep_seconds
                            existing.awake_seconds = hs.awake_seconds
                            existing.time_in_bed_seconds = hs.time_in_bed_seconds
            except Exception as e:
                print(f"Warning: Failed to import Sleep data: {e}")

        def insert_daily_metrics(importer, metric_type, unit):
            try:
                values = importer.get_data(start, end)
                dates = getattr(importer, 'dates', [])
                
                # Fetch existing metrics in bulk to avoid individual N+1 selects
                existing_metrics_dict = {
                    m.timestamp: m for m in session.query(HealthMetric).filter(
                        HealthMetric.user_id == user_id,
                        HealthMetric.metric_type == metric_type,
                        HealthMetric.timestamp >= datetime.combine(start, datetime.min.time()),
                        HealthMetric.timestamp <= datetime.combine(end, datetime.max.time())
                    ).all()
                }
                
                for d, val in zip(dates, values):
                    if val is not None and d is not None:
                        # For daily metrics, it's already a date, so applying tz offset at midnight is less relevant,
                        # but we still record the timezone context explicitly.
                        tz_name = get_timezone_for_date(
                            d, holidays, default_tz)
                        dt = datetime.combine(d, datetime.min.time())

                        existing = existing_metrics_dict.get(dt)

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
                            existing_metrics_dict[dt] = m  # Track newly added to avoid duplicates if feed has them
                        else:
                            existing.value = val
                            existing.unit = unit
                            existing.timezone = tz_name
            except Exception as e:
                print(f"Warning: Failed to import {metric_type}: {e}")

        if 'resting_heart_rate' in types_to_run:
            print("Importing Resting Heart Rate...")
            try:
                insert_daily_metrics(fo.RestingHeartRate(
                    data_source), 'resting_heart_rate', 'bpm')
            except AttributeError:
                print("Warning: RestingHeartRate not found in fitout")

        if 'breathing_rate' in types_to_run:
            print("Importing Breathing Rate...")
            try:
                insert_daily_metrics(fo.BreathingRate(
                    data_source, precision=1), 'breathing_rate', 'breaths/min')
            except AttributeError:
                print("Warning: BreathingRate not found in fitout")

        if 'hrv' in types_to_run:
            print("Importing Heart Rate Variability...")
            try:
                insert_daily_metrics(fo.HeartRateVariability(
                    data_source), 'hrv_rmssd', 'ms')
            except AttributeError:
                print("Warning: HeartRateVariability not found in fitout")
            except Exception as e:
                print(f"Warning: Failed to import HRV: {e}")

        if 'exercises' in types_to_run:
            print("Importing Exercises...")
            try:
                # We need timedelta here, verify it's imported at the top. Let's use `from datetime import datetime, date, timedelta` if not, or add timedelta if it's missing. I'll check imports later.
                from datetime import timedelta

                exercise_importer = fo.ExerciseInfo(data_source)
                exercise_data_raw = exercise_importer.get_raw_sessions(
                    start, end)

                for ex in exercise_data_raw:
                    # Google TakeOut exports startTimeIso timestamps as UTC Time (disguised without a Z).
                    # We should shift it by UTC offsets
                    dt_start_utc = None
                    try:
                        dt_start_utc = datetime.fromisoformat(
                            ex.get('startTimeIso'))
                    except (ValueError, TypeError):
                        continue

                    tz_name = get_timezone_for_date(
                        dt_start_utc.date() if dt_start_utc else None, holidays, default_tz)
                    dt_start, tz_used = convert_utc_to_local(
                        dt_start_utc, tz_name)

                    # Fitbit provides milliseconds
                    duration_s = ex.get('duration', 0) // 1000
                    dt_end = dt_start + timedelta(seconds=duration_s)

                    # metadata = {
                    #     "activity_name": ex.get('activityName'),
                    #     "calories": ex.get('calories'),
                    #     "steps": ex.get('steps'),
                    #     "average_heart_rate": ex.get('averageHeartRate'),
                    #     "log_id": ex.get('logId')
                    # }

                    # # Remove None values from metadata
                    # metadata = {k: v for k, v in metadata.items()
                    #             if v is not None}

                    # Get the unique ID of this exercise from the "logId"
                    # It is safe to cast to int, as Google TakeOut logId is a number
                    log_id = int(ex.get('logId')) if ex.get('logId') else None

                    hs = ExerciseSession(
                        global_id=log_id,
                        user_id=user_id,
                        source_id=FITBIT_SOURCE_ID,
                        start_time=dt_start,
                        end_time=dt_end,
                        duration_seconds=duration_s,
                        timezone=tz_used,
                        metadata_json=json.dumps(ex),
                        activity_name=ex.get('activityName', 'Unknown'),
                        steps=ex.get('steps', 0),
                        calories_burned=ex.get('calories', 0.0),
                        distance_km=ex.get('distance', 0.0),
                        average_heart_rate=ex.get('averageHeartRate', 0)
                    )

                    if log_id:
                        existing = session.query(ExerciseSession).filter_by(
                            global_id=log_id).first()
                    else:
                        existing = session.query(ExerciseSession).filter_by(
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
                        existing.activity_name = hs.activity_name
                        existing.steps = hs.steps
                        existing.calories_burned = hs.calories_burned
                        existing.distance_km = hs.distance_km
                        existing.average_heart_rate = hs.average_heart_rate

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
                        dt_utc = datetime.fromisoformat(
                            w_entry.get('startTimeIso'))
                    except (ValueError, TypeError):
                        continue

                    # Google TakeOut exports weight timestamps as Naive Local Time (disguised without a Z).
                    # We should NOT shift it by UTC offsets, just format it naively as-is.
                    dt = dt_utc.replace(tzinfo=None)
                    tz_name = get_timezone_for_date(
                        dt.date() if dt else None, holidays, default_tz)
                    tz_used = tz_name

                    # Insert weight
                    val_weight = w_entry.get('weight')
                    if val_weight is not None:
                        if weight_to_kgs:
                            unit = 'kg'
                            # Convert lbs to kg, 1 decimal
                            val_weight = round(val_weight / 2.20462262, 1)
                        else:
                            unit = 'lb'

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
                                value=val_weight,
                                unit=unit,
                                timestamp=dt,
                                timezone=tz_used
                            )
                            session.add(m)
                        else:
                            existing.value = val_weight
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


def main():
    parser = argparse.ArgumentParser(
        description="Ingest FitOut unzipped data into MeasureMe database.")
    parser.add_argument(
        'path', type=str, help='Path to the unzipped Google/Fitbit Export directory')
    parser.add_argument(
        '--db', type=str, default='sqlite:///measureme_dev.db', help='SQLAlchemy Database URL')
    parser.add_argument('--start', type=str, required=True,
                        help='Start date YYYY-MM-DD')
    parser.add_argument('--end', type=str, required=True,
                        help='End date YYYY-MM-DD')
    parser.add_argument(
        '--types', nargs='+', help='Specify which health types to import (e.g. sleep exercises resting_heart_rate). Defaults to all.')
    parser.add_argument('--user-id', type=int, default=1,
                        help='User ID to associate with the imported data. Defaults to 1.')
    parser.add_argument('--holidays-csv', type=str,
                        help='Path to a CSV file containing holiday dates to calculate proper timezones.')
    parser.add_argument('--timezone', type=str, default='Europe/London',
                        help='The default IANA timezone to use (e.g. Europe/London).')
    parser.add_argument('--weight-to-kgs', action='store_true',
                        help='Set this flag if the TakeOut weight data was exported in pounds (lbs), to auto-convert to kg.')

    args = parser.parse_args()

    s_date = datetime.strptime(args.start, '%Y-%m-%d').date()
    e_date = datetime.strptime(args.end, '%Y-%m-%d').date()

    process_export(args.path, args.db, s_date, e_date, args.types,
                   args.user_id, args.holidays_csv, args.timezone, args.weight_to_kgs)


if __name__ == "__main__":
    main()

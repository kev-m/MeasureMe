import json
import logging

from measureme import models
from datetime import datetime, timedelta

from fitbit_client import FitbitClient

log = logging.getLogger('FitbitCommon')


class FitbitDataMapper:
    def __init__(self, db_session, tz_name: str = "UTC"):
        self.db = db_session
        self.user_id = 1
        self.source_id = 1  # Assuming 1 = Fitbit
        self.tz_name = tz_name
        self.tz_info = __import__('zoneinfo').ZoneInfo(tz_name)

    def upsert_metric(self, metric_type: str, val: float, unit: str, dt: datetime):
        existing = self.db.query(models.HealthMetric).filter_by(
            user_id=self.user_id, metric_type=metric_type, timestamp=dt
        ).first()
        if not existing:
            m = models.HealthMetric(
                user_id=self.user_id, source_id=self.source_id,
                metric_type=metric_type, value=val, unit=unit, timestamp=dt, timezone=self.tz_name
            )
            self.db.add(m)
        else:
            existing.value = val
            existing.unit = unit
            existing.timezone = self.tz_name

    def process_sleep(self, sleep_data: dict):
        sleep_entries = sleep_data.get('sleep', [])
        for entry in sleep_entries:
            start_str = entry.get('startTime')
            end_str = entry.get('endTime')
            if not start_str or not end_str:
                continue

            start_time = datetime.fromisoformat(start_str)
            end_time = datetime.fromisoformat(end_str)

            # It is safe to cast to int, as FitBit logId is a number
            log_id = int(entry.get('logId')) if entry.get('logId') else None
            start_time_tz = start_time.replace(tzinfo=self.tz_info)

            existing = self.db.query(models.SleepSession).filter_by(
                global_id=log_id
            ).first()

            # If not existing, check for an existing sleep on the same day, within 2 hours
            if not existing:
                duration_s = entry.get('minutesAsleep', 0) * 60
                # Fallback heuristic: matching duration within +/- 24 hours
                tw_start = start_time_tz - timedelta(hours=2)
                tw_end = start_time_tz + timedelta(hours=2)
                potentials = self.db.query(models.SleepSession).filter(
                    models.SleepSession.user_id == self.user_id,
                    models.SleepSession.is_main_sleep == entry.get(
                        'isMainSleep', True),
                    models.SleepSession.start_time >= tw_start,
                    models.SleepSession.start_time <= tw_end
                ).all()
                for p in potentials:
                    if abs(p.duration_seconds - duration_s) <= 60*60:  # Within 60 minutes duration
                        existing = p
                        break

            # 1. Prune the telemetry noise
            # Drop the levels.data and levels.shortData details
            if 'levels' in entry:
                entry['levels'].pop('data', None)
                entry['levels'].pop('shortData', None)

            # Drop the minuteData details
            entry.pop('minuteData', None)

            # 2. Pre-calculate common values
            duration = entry.get('minutesAsleep', 0) * 60
            metadata = json.dumps(entry)

            levels_summary = entry.get('levels', {}).get('summary', {})

            if not existing:
                session = models.SleepSession(
                    global_id=log_id,
                    user_id=self.user_id,
                    source_id=self.source_id,
                    start_time=start_time,
                    end_time=end_time,
                    duration_seconds=duration,
                    timezone=self.tz_name,
                    metadata_json=metadata,
                    is_main_sleep=entry.get('isMainSleep', True),
                    efficiency_score=entry.get('efficiency', 0),
                    deep_sleep_seconds=levels_summary.get(
                        'deep', {}).get('minutes', 0) * 60,
                    light_sleep_seconds=levels_summary.get(
                        'light', {}).get('minutes', 0) * 60,
                    rem_sleep_seconds=levels_summary.get(
                        'rem', {}).get('minutes', 0) * 60,
                    awake_seconds=levels_summary.get(
                        'wake', {}).get('minutes', 0) * 60,
                    time_in_bed_seconds=entry.get('timeInBed', 0) * 60
                )
                self.db.add(session)
            else:
                existing.start_time = start_time  # Update the start time, too!
                existing.end_time = end_time
                existing.duration_seconds = duration
                existing.timezone = self.tz_name
                existing.metadata_json = metadata
                existing.is_main_sleep = entry.get('isMainSleep', True)
                existing.efficiency_score = entry.get('efficiency', 0)
                existing.deep_sleep_seconds = levels_summary.get(
                    'deep', {}).get('minutes', 0) * 60
                existing.light_sleep_seconds = levels_summary.get(
                    'light', {}).get('minutes', 0) * 60
                existing.rem_sleep_seconds = levels_summary.get(
                    'rem', {}).get('minutes', 0) * 60
                existing.awake_seconds = levels_summary.get(
                    'wake', {}).get('minutes', 0) * 60
                existing.time_in_bed_seconds = entry.get('timeInBed', 0) * 60
        self.db.commit()

    def process_activities(self, activities_data: dict, date_str: str):
        summary = activities_data.get('summary', {})
        dt = datetime.strptime(date_str, "%Y-%m-%d")

        if summary:
            if 'steps' in summary:
                self.upsert_metric('steps', float(
                    summary['steps']), 'count', dt)
            if 'restingHeartRate' in summary:
                self.upsert_metric('resting_heart_rate', float(
                    summary['restingHeartRate']), 'bpm', dt)

        # Process discrete workout exercises directly from the 'activities' array
        for act in activities_data.get('activities', []):
            start_str = act.get('startDate') + 'T' + act.get('startTime')
            try:
                start_time = datetime.fromisoformat(start_str)
            except Exception:
                continue

            # It is safe to cast to int, as FitBit logId is a number
            log_id = int(act.get('logId')) if act.get('logId') else None

            averageHeartRate = act.get('averageHeartRate', 0)
            if averageHeartRate == 0:
                # Try and get from summary
                # TODO: Compute from intraday data
                pass

            dur_ms = act.get('duration', 0)
            end_time = start_time + timedelta(milliseconds=dur_ms)
            duration_s = dur_ms // 1000

            existing = self.db.query(models.ExerciseSession).filter_by(
                global_id=log_id  # str(act.get('logId'))
            ).first()

            if not existing:
                log.info("Unable to find activity with ID %s, trying fallback", log_id)
                # Fallback heuristic: matching duration within +/- 24 hours
                tw_start = start_time - timedelta(hours=24)
                tw_end = start_time + timedelta(hours=24)
                potentials = self.db.query(models.ExerciseSession).filter(
                    models.ExerciseSession.user_id == self.user_id,
                    models.ExerciseSession.start_time >= tw_start,
                    models.ExerciseSession.start_time <= tw_end
                ).all()
                for p in potentials:
                    if abs(p.duration_seconds - duration_s) <= 5:
                        existing = p
                        log.info("Found replacement activity of ID %s with ID %s", log_id, p.global_id)
                        break

            if not existing:
                session = models.ExerciseSession(
                    global_id=log_id,  # str(act.get('logId')),
                    user_id=self.user_id,
                    source_id=self.source_id,
                    start_time=start_time,
                    end_time=end_time,
                    duration_seconds=duration_s,
                    timezone=self.tz_name,
                    metadata_json=json.dumps(act),
                    activity_name=act.get('name', 'Unknown'),
                    steps=act.get('steps', 0),
                    calories_burned=act.get('calories', 0.0),
                    distance_km=act.get('distance', 0.0),
                    average_heart_rate=averageHeartRate
                )
                self.db.add(session)
            else:
                # Note: API might have a different `logId`, let's not overwrite the log_id if it matched by duration,
                # but we could update the metadata to match the latest API response.
                existing.start_time = start_time
                existing.end_time = end_time
                existing.duration_seconds = duration_s
                existing.timezone = self.tz_name
                existing.metadata_json = json.dumps(act)
                existing.activity_name = act.get('name', 'Unknown')
                existing.steps = act.get('steps', 0)
                existing.calories_burned = act.get('calories', 0.0)
                existing.distance_km = act.get('distance', 0.0)
                existing.average_heart_rate = averageHeartRate
        self.db.commit()

    def process_heart_rate(self, hr_data: dict, date_str: str):
        # Resting HR
        dt_base = datetime.strptime(date_str, "%Y-%m-%d")
        for hr_day in hr_data.get('activities-heart', []):
            rhr = hr_day.get('value', {}).get('restingHeartRate')
            if rhr:
                self.upsert_metric('resting_heart_rate',
                                   float(rhr), 'bpm', dt_base)

        # Intraday (Telemetry)
        # Extract heart_rate_id using the key 'heart_rate'
        heart_rate_id = models.MetricTypeFromString('heart_rate')
        for point in hr_data.get('activities-heart-intraday', {}).get('dataset', []):
            time_str = point.get('time')
            val = point.get('value')
            if time_str and val is not None:
                # Apply the current timezone configuration before calculating UTC timestamp
                dt_point = datetime.strptime(
                    f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=self.tz_info)
                hi = models.HealthIntraday(
                    timestamp_utc=int(dt_point.timestamp()),
                    user_id=self.user_id,
                    metric_type_id=heart_rate_id,
                    value=float(val)
                )
                self.db.merge(hi)
        self.db.commit()

    def process_breathing_rate(self, data: dict):
        for entry in data.get('br', []):
            dt_str = entry.get('dateTime')
            value = entry.get('value', {})
            summary = value.get('fullSleepSummary', {})
            val = summary.get('breathingRate')
            if dt_str and val is not None:
                dt = datetime.strptime(dt_str, "%Y-%m-%d")
                self.upsert_metric(
                    'breathing_rate', float(val), 'breaths/min', dt)
        self.db.commit()

    def process_hrv(self, data: dict):
        for entry in data.get('hrv', []):
            dt_str = entry.get('dateTime')
            val = entry.get('value', {}).get('dailyRmssd')
            if dt_str and val is not None:
                dt = datetime.strptime(dt_str, "%Y-%m-%d")
                self.upsert_metric('hrv_rmssd', float(val), 'ms', dt)
        self.db.commit()

    def process_weight(self, data: dict):
        for entry in data.get('weight', []):
            dt_str = entry.get('date')
            time_str = entry.get('time', '00:00:00')
            if dt_str:
                dt = datetime.strptime(
                    f"{dt_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                if entry.get('weight') is not None:
                    self.upsert_metric('weight', float(
                        entry.get('weight')), 'kg', dt)
                if entry.get('bmi') is not None:
                    self.upsert_metric('bmi', float(
                        entry.get('bmi')), 'index', dt)
                if entry.get('fat') is not None:
                    self.upsert_metric('body_fat', float(
                        entry.get('fat')), 'percent', dt)
        self.db.commit()


class FitbitFetcher:
    """Consolidates Fitbit API endpoint URLs and data mapping coordination."""

    def __init__(self, client: FitbitClient, mapper: FitbitDataMapper):
        self.client = client
        self.mapper = mapper

    def fetch_and_process(self, collection_type: str, date_str: str, is_webhook: bool = False):
        """Fetch a specific collection type for a specific date and process it via mapper."""
        log.info(f"Fetching updated {collection_type} data for {date_str}...")
        try:
            if collection_type == 'sleep':
                # Use Version 1.2 API
                data = self.client.fetch_data(
                    f"https://api.fitbit.com/1.2/user/-/sleep/date/{date_str}.json")
                log.debug(f"Raw sleep data from API: {json.dumps(data)}")
                log.info(
                    f"Successfully fetched {len(data.get('sleep', []))} sleep records.")
                self.mapper.process_sleep(data)

                if is_webhook:
                    # Webhooks only tell us about 'sleep', not BR or HRV. We opportunistically grab them.
                    try:
                        br_data = self.client.fetch_data(
                            f"br/date/{date_str}/all.json")
                        self.mapper.process_breathing_rate(br_data)
                    except Exception as e:
                        log.debug(f"No breathing rate for {date_str}: {e}")

                    try:
                        hrv_data = self.client.fetch_data(
                            f"hrv/date/{date_str}.json")
                        self.mapper.process_hrv(hrv_data)
                    except Exception as e:
                        log.debug(f"No HRV for {date_str}: {e}")

            elif collection_type == 'breathing_rate':
                br_data = self.client.fetch_data(
                    f"br/date/{date_str}/all.json")
                log.debug(f"Raw br_data from API: {json.dumps(br_data)}")
                self.mapper.process_breathing_rate(br_data)

            elif collection_type == 'hrv':
                hrv_data = self.client.fetch_data(f"hrv/date/{date_str}.json")
                log.debug(f"Raw hrv_data from API: {json.dumps(hrv_data)}")
                self.mapper.process_hrv(hrv_data)

            elif collection_type == 'activities' or collection_type == 'exercises':
                data = self.client.fetch_data(
                    f"activities/date/{date_str}.json")
                log.debug(f"Raw activity data from API: {json.dumps(data)}")
                log.info("Successfully fetched activity records.")
                self.mapper.process_activities(data, date_str)

                if collection_type == 'activities' and is_webhook:
                    # Webhooks group intraday HR under 'activities', grab it.
                    try:
                        hr_data = self.client.fetch_data(
                            f"activities/heart/date/{date_str}/1d/1min.json")
                        self.mapper.process_heart_rate(hr_data, date_str)
                    except Exception as e:
                        log.debug(f"No intraday HR for {date_str}: {e}")

            elif collection_type == 'resting_heart_rate' or collection_type == 'intraday_heart_rate':
                hr_data = self.client.fetch_data(
                    f"activities/heart/date/{date_str}/1d/1min.json")
                self.mapper.process_heart_rate(hr_data, date_str)

            elif collection_type == 'body' or collection_type == 'weight':
                try:
                    body_data = self.client.fetch_data(
                        f"body/log/weight/date/{date_str}.json")
                    self.mapper.process_weight(body_data)
                    log.info(
                        f"Successfully fetched weight records for {date_str}.")
                except Exception as e:
                    log.debug(f"No weight for {date_str}: {e}")

            else:
                log.warning(
                    f"No specific handler yet for live sync of collection: {collection_type}")

        except Exception as api_err:
            log.error(
                f"API Error fetching {collection_type}: {api_err}", exc_info=True)
            raise

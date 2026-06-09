"""
Common utilities shared between the background web ingestor, the Flask blueprints, 
and the standalone CLI `ingest_ghealth.py`.

Contains database mappers and the GHealthFetcher for interacting with the Google Health API.
"""
import json
import hashlib
import logging
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build_from_document

from measureme.models import ExerciseSession, SleepSession, HealthMetric, HealthIntraday

log = logging.getLogger(__name__)

# Scopes needed for Google Health Connect REST API processing
SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.location.readonly",
    "https://www.googleapis.com/auth/googlehealth.nutrition.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.ecg.readonly"
]

BASIC_TYPES = ['sleep', 'exercise', 'weight', 'hrv', 'resting_heart_rate', 'breathing_rate']
ALL_TYPES = BASIC_TYPES + ['intraday_heart_rate']


def load_credentials(token_path: str) -> Credentials:
    """Loads Google credentials from the local token.json file and refreshes if expired."""
    creds = None
    if Path(token_path).exists():
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception as e:
            log.error(f"Error loading tokens: {e}")

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save refreshed credentials back to disk
            with open(token_path, 'w') as token_file:
                token_file.write(creds.to_json())
        except Exception as e:
            log.error(f"Error refreshing tokens: {e}")
            creds = None

    return creds


def extract_global_id(point_name: str) -> int:
    try:
        global_id_str = point_name.split('/')[-1]
        global_id = int(global_id_str)
    except Exception as e:
        hasher = hashlib.sha1(point_name.encode('utf-8'))
        global_id = int(hasher.hexdigest()[:15], 16)

    return global_id


TZ_CACHE = {}


def extract_start_end_times(tz_info, interval: Dict[str, Any]) -> tuple[str, datetime, datetime]:
    start_str = interval.get('startTime')
    end_str = interval.get('endTime')

    start_offset_str = interval.get('startUtcOffset', '0s')
    end_offset_str = interval.get('endUtcOffset', '0s')

    if not start_str or not end_str:
        raise ValueError("No start or end time in %s", interval)

    # "2024-03-31T03:00:00Z"
    start_dt_utc = datetime.strptime(start_str.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
    end_dt_utc = datetime.strptime(end_str.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")

    start_offset_sec = int(start_offset_str.replace('s', ''))
    end_offset_sec = int(end_offset_str.replace('s', ''))

    # Embedded naive local time according to the vendor's offset
    emb_start_time = start_dt_utc.replace(tzinfo=None) + timedelta(seconds=start_offset_sec)
    emb_end_time = end_dt_utc.replace(tzinfo=None) + timedelta(seconds=end_offset_sec)

    if tz_info:
        start_time = start_dt_utc.astimezone(tz_info).replace(tzinfo=None)
        end_time = end_dt_utc.astimezone(tz_info).replace(tzinfo=None)
        return str(tz_info), start_time, end_time
    else:
        # Use the embedded offset as fallback
        start_time = emb_start_time
        end_time = emb_end_time

        # Compute a time zone name, too
        if start_offset_str not in TZ_CACHE:
            # First try to map the offset to a real IANA timezone name by checking
            # available zoneinfo zones for a zone that has the same offset at the
            # start datetime. This is best-effort and may return the first match.
            tz_name_from_offset = None

            # try:
            #     from zoneinfo import available_timezones
            #     start_dt_aware = start_dt_utc
            #     for candidate in available_timezones():
            #         try:
            #             zi = ZoneInfo(candidate)
            #             if start_dt_aware.astimezone(zi).utcoffset().total_seconds() == start_offset_sec:
            #                 tz_name_from_offset = candidate
            #                 break
            #         except Exception:
            #             continue
            # except Exception:
            #     tz_name_from_offset = None

            # Fallback to a UTC±HH:MM string if no IANA name was found
            if not tz_name_from_offset:
                secs = start_offset_sec
                sign = '+' if secs >= 0 else '-'
                abs_secs = abs(secs)
                hours = abs_secs // 3600
                minutes = (abs_secs % 3600) // 60
                tz_name_from_offset = f"UTC{sign}{hours:02d}:{minutes:02d}"

            TZ_CACHE[start_offset_str] = tz_name_from_offset

    return TZ_CACHE[start_offset_str], start_time, end_time


class GHealthDataMapper:
    """Maps Google Health API responses to MeasureMe models."""

    def __init__(self, db_session, tz_name: str = "UTC"):
        self.db = db_session
        self.user_id = 1
        self.source_id = 2  # Assuming 2 = Google Health (1 = Fitbit usually)
        self.tz_name = tz_name

        # Safely import zoneinfo where required
        try:
            self.tz_info = ZoneInfo(tz_name)
        except:
            self.tz_info = None

    def process_data_points_by_type(self, collection_type: str, data_points: List[Dict[str, Any]]):
        """
        Processes data points of a specific type. Useful for directed fetching.
        """
        # Google Health API is returned points in reverse time order.
        for point in reversed(data_points):
            if collection_type == 'sleep':
                self._process_sleep_session(point)
            elif collection_type == 'exercise':
                self._process_exercise_session(point)
            elif collection_type == 'weight':
                self._process_health_metric(point, 'weight', 'weight', 'kg')
            elif collection_type == 'resting_heart_rate':
                self._process_health_metric(point, 'dailyRestingHeartRate', 'resting_heart_rate', 'bpm')
            elif collection_type == 'hrv':
                self._process_health_metric(point, 'dailyHeartRateVariability', 'hrv_rmssd', 'ms')
            elif collection_type == 'breathing_rate':
                self._process_health_metric(point, 'respiratoryRateSleepSummary', 'breathing_rate', 'breaths/min')
            elif collection_type == 'intraday_heart_rate':
                self._process_health_intraday(point, 'heartRate', 1)

        self.db.commit()

    def _process_health_metric(self, point: Dict[str, Any], api_key: str, metric_type: str, unit: str):
        data = point.get(api_key, {})
        if not data:
            return

        # Sometimes used to extract global_id
        point_name = point.get('name', '')

        # Get timestamp
        timestamp = None
        if 'date' in data:
            # e.g., "2024-03-31" or similar
            date_obj = data['date']
            if date_obj.get('year') and date_obj.get('month') and date_obj.get('day'):
                try:
                    timestamp = datetime(date_obj['year'], date_obj['month'], date_obj['day'])
                except ValueError:
                    pass
        elif 'sampleTime' in data:
            # e.g., "2024-03-31T03:00:00Z"
            time_obj = data['sampleTime']
            if isinstance(time_obj, dict):
                time_str = time_obj.get('physicalTime') or time_obj.get('logicalTime') or ''
            else:
                time_str = str(time_obj)

            if time_str:
                try:
                    # Google API sometimes returns sub-second precision that strptime doesn't like if too long
                    # or missing Z. We'll handle Z and then try basic parsing.
                    clean_time = time_str.replace("Z", "+0000")
                    if '.' in clean_time:
                        # Truncate fractional seconds to 6 digits (microseconds)
                        parts = clean_time.split('.')
                        time_part = parts[0]
                        frac_part = parts[1][:6] if '+' not in parts[1] else parts[1].split('+')[0][:6]
                        tz_part = parts[1].split('+')[1] if '+' in parts[1] else '0000'
                        clean_time = f"{time_part}.{frac_part}+{tz_part}"
                        timestamp = datetime.strptime(clean_time, "%Y-%m-%dT%H:%M:%S.%f%z").replace(tzinfo=None)
                    else:
                        timestamp = datetime.strptime(clean_time, "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None)
                except Exception:
                    log.warning(f"Failed to parse time string: {time_str}")

        if not timestamp:
            return

        # Default global_id for non-identified types is the timestamp.
        # Identified types override the global_id on an individual basis.
        # NOTE: This only works in this context because the credentials are for a single user,
        #       so that all data in this database is for *this* user.
        # TODO: At some point in the future, will need a more generic global_id from time algorithm.
        #       Probably one that takes some kind of inject "this user id prefix" that offsets the timestamp?
        global_id = int(timestamp.timestamp() * 1000)
        # Have to do a correction, as all daily metrics have the same timestamp
        global_id += len(metric_type)

        # Get value
        value = None
        if api_key == 'weight':
            if not point_name:
                log.warning("Point name not found for metric '%s'", metric_type)
                return
            global_id = extract_global_id(point_name)
            weight_grams = data.get('weightGrams')
            if weight_grams:
                value = weight_grams / 1000.0
        elif api_key == 'dailyRestingHeartRate':
            # beatsPerMinute is often a string in the API
            bpm = data.get('beatsPerMinute')
            if bpm is not None:
                value = round(float(bpm), 1)
        elif api_key == 'dailyHeartRateVariability':
            hrv = data.get('averageHeartRateVariabilityMilliseconds')
            if hrv is not None:
                value = round(float(hrv), 1)
        elif api_key == 'respiratoryRateSleepSummary':
            stats = data.get('fullSleepStats', {})
            br = stats.get('breathsPerMinute')
            if br is not None:
                value = round(float(br), 1)

        if value is None:
            return

        existing = self.db.query(HealthMetric).filter(HealthMetric.global_id == global_id).first()
        if not existing:
            metric_record = HealthMetric(global_id=global_id,
                                         user_id=self.user_id,
                                         source_id=self.source_id,
                                         metric_type=metric_type,
                                         value=value,
                                         unit=unit,
                                         timestamp=timestamp,
                                         timezone=self.tz_name)
            self.db.add(metric_record)
        else:
            existing.value = value
            existing.timestamp = timestamp
            existing.metric_type = metric_type
            existing.unit = unit

    def _process_health_intraday(self, point: Dict[str, Any], api_key: str, metric_type_id: int):
        data = point.get(api_key, {})
        if not data:
            return

        time_obj = data.get('sampleTime')
        if not time_obj:
            # Check point-level startTime (used in aggregate/rollUp results)
            time_obj = point.get('startTime')

        if not time_obj:
            return

        if isinstance(time_obj, dict):
            time_str = time_obj.get('physicalTime') or time_obj.get('logicalTime') or ''
        else:
            time_str = str(time_obj)

        if not time_str:
            return

        try:
            # Truncate fractional seconds to 6 digits (microseconds) if necessary for strptime %f
            if '.' in time_str:
                parts = time_str.split('.')
                if len(parts) > 1:
                    # Keep only up to 6 digits of fractional seconds before 'Z' or '+'
                    suffix = ""
                    if "Z" in parts[1]:
                        suffix = "Z"
                        frac = parts[1].split("Z")[0]
                    elif "+" in parts[1]:
                        suffix = "+" + parts[1].split("+")[1]
                        frac = parts[1].split("+")[0]
                    else:
                        frac = parts[1]

                    time_str = parts[0] + "." + frac[:6] + suffix

            if '.' in time_str:
                timestamp_utc = int(
                    datetime.strptime(time_str.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z").timestamp())
            else:
                timestamp_utc = int(
                    datetime.strptime(time_str.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z").timestamp())
        except ValueError:
            return

        value = None
        if api_key == 'heartRate':
            # Raw bpm
            bpm = data.get('beatsPerMinute')
            if bpm is None:
                # Rollup average
                bpm = data.get('beatsPerMinuteAvg')

            if bpm is not None:
                # Round to integer
                value = round(float(bpm), 0)

        if not value:
            return

        # Intraday uses (timestamp_utc, user_id, metric_type_id) as PK
        existing = self.db.query(HealthIntraday).filter(HealthIntraday.timestamp_utc == timestamp_utc,
                                                        HealthIntraday.user_id == self.user_id,
                                                        HealthIntraday.metric_type_id == metric_type_id).first()

        if not existing:
            intraday_record = HealthIntraday(timestamp_utc=timestamp_utc,
                                             user_id=self.user_id,
                                             metric_type_id=metric_type_id,
                                             value=value)
            self.db.add(intraday_record)
        else:
            existing.value = value

    def extract_sleep_summary(self, summary_data: List[Dict], key: str):
        """Extract the key from the summary data.

        Given:
            "stagesSummary": [
            {
                "type": "AWAKE",
                "minutes": "35",
                "count": "19"
            },
            {
                "type": "LIGHT",
                "minutes": "292",
                "count": "21"
            },
            {
                "type": "DEEP",
                "minutes": "57",
                "count": "3"
            },
            {
                "type": "REM",
                "minutes": "121",
                "count": "14"
            }
            ]
        """
        try:
            for entry in summary_data:
                if entry.get('type', '') == key:
                    return int(entry.get('minutes', 0))
        except Exception as e:
            log.exception("Exception parsing sleep_summary: %s", str(e))
            return 0
        return 0

    def _process_sleep_session(self, point: Dict[str, Any]):
        # ID can come from point name: e.g. "users/me/dataTypes/sleep/dataPoints/12345"
        point_name = point.get('name', '')

        entry = point.get('sleep', {})
        # Data clean-up, remove excessive details: stages
        entry.pop('stages', None)

        interval = entry.get('interval', {})
        try:
            tz_name, start_time, end_time = extract_start_end_times(self.tz_info, interval)
        except ValueError:
            return

        if not point_name:
            # Fallback for types that don't have a unique 'name' resource path
            point_name = f"ghealth_sleep_{start_time.strftime('%Y%m%d%H%M%S')}"

        global_id = extract_global_id(point_name)

        metadata = json.dumps(entry)
        summary = entry.get('summary', {})
        levels_summary = summary.get('stagesSummary', {})

        duration_minutes = int(summary.get('minutesAsleep', 0))

        # Upsert logic
        existing = self.db.query(SleepSession).filter(SleepSession.global_id == global_id).first()
        if not existing:
            sleep_record = SleepSession(
                global_id=global_id,
                user_id=self.user_id,
                source_id=self.source_id,
                start_time=start_time,
                end_time=end_time,
                duration_minutes=duration_minutes,
                timezone=tz_name,
                metadata_json=metadata,
                # Others
                is_main_sleep=entry.get('type', '') == 'STAGES',
                # efficiency_score=efficiency,
                deep_sleep_minutes=self.extract_sleep_summary(levels_summary, 'DEEP'),
                light_sleep_minutes=self.extract_sleep_summary(levels_summary, 'LIGHT'),
                rem_sleep_minutes=self.extract_sleep_summary(levels_summary, 'REM'),
                awake_minutes=self.extract_sleep_summary(levels_summary, 'AWAKE'),
                time_in_bed_minutes=int(summary.get('minutesInSleepPeriod', 0)))
            self.db.add(sleep_record)
        else:
            existing.start_time = start_time
            existing.end_time = end_time
            existing.duration_minutes = duration_minutes
            existing.metadata_json = metadata
            existing.timezone = tz_name
            # Others
            existing.is_main_sleep = entry.get('type', '') == 'STAGES'
            existing.deep_sleep_minutes = self.extract_sleep_summary(levels_summary, 'DEEP')
            existing.light_sleep_minutes = self.extract_sleep_summary(levels_summary, 'LIGHT')
            existing.rem_sleep_minutes = self.extract_sleep_summary(levels_summary, 'REM')
            existing.awake_minutes = self.extract_sleep_summary(levels_summary, 'AWAKE')
            existing.time_in_bed_minutes = int(summary.get('minutesInSleepPeriod', 0))

    def _process_exercise_session(self, point: Dict[str, Any]):

        point_name = point.get('name', '')
        entry = point.get('exercise', {})

        interval = entry.get('interval', {})
        try:
            tz_name, start_time, end_time = extract_start_end_times(self.tz_info, interval)
        except ValueError:
            return

        global_id = extract_global_id(point_name)

        duration_seconds = int((end_time - start_time).total_seconds())
        metadata = json.dumps(entry)

        activity_type = entry.get('exerciseType', 'UNKNOWN')
        activity_name = entry.get('displayName', activity_type)

        summary = entry.get('summary', {})
        metrics_summary = summary.get('metricsSummary', {})

        # Upsert logic
        existing = self.db.query(ExerciseSession).filter(ExerciseSession.global_id == global_id).first()
        if not existing:
            exercise_record = ExerciseSession(global_id=global_id,
                                              user_id=self.user_id,
                                              source_id=self.source_id,
                                              start_time=start_time,
                                              end_time=end_time,
                                              duration_seconds=duration_seconds,
                                              activity_name=activity_name[:100],
                                              timezone=tz_name,
                                              metadata_json=metadata,
                                              steps=int(metrics_summary.get('steps', 0)),
                                              calories_burned=float(metrics_summary.get('caloriesKcal', 0)),
                                              distance_km=float(metrics_summary.get('distanceMillimeters', 0)) / 1000,
                                              average_heart_rate=int(
                                                  metrics_summary.get('averageHeartRateBeatsPerMinute', 0)))
            self.db.add(exercise_record)
        else:
            existing.start_time = start_time
            existing.end_time = end_time
            existing.duration_seconds = duration_seconds
            existing.activity_name = activity_name[:100]
            existing.metadata_json = metadata
            existing.timezone = tz_name
            existing.steps = int(metrics_summary.get('steps', 0))
            existing.calories_burned = float(metrics_summary.get('caloriesKcal', 0))
            existing.distance_km = float(metrics_summary.get('distanceMillimeters', 0)) / 1000
            existing.average_heart_rate = int(metrics_summary.get('averageHeartRateBeatsPerMinute', 0))


class GHealthFetcher:
    """
    Encapsulates fetching Google Health data using the googleapiclient
    and delegating data mapping to GHealthDataMapper.
    """

    def __init__(self, credentials: Credentials, mapper: GHealthDataMapper):

        if not credentials or not credentials.valid:
            raise ValueError("Valid Google credentials are required to initialize GHealthFetcher.")
        self.credentials = credentials
        self.mapper = mapper

        # Build the official Google Health API resource directly from the discovery rest document
        discovery_path = os.path.join(os.path.dirname(__file__), 'health_api_discovery_rest.json')
        with open(discovery_path, 'r', encoding='utf-8') as f:
            discovery_doc = f.read()

        self.service = build_from_document(json.loads(discovery_doc), credentials=self.credentials)

    def get_query_params(self, collection_type: str, start_date: datetime, end_date: datetime):
        """Returns (parent, filter_expr) for the given collection and date range."""
        start_str_rfc = start_date.strftime('%Y-%m-%dT00:00:00.000Z')
        end_str_rfc = end_date.strftime('%Y-%m-%dT23:59:59.999Z')
        start_str_civil = start_date.strftime('%Y-%m-%dT00:00:00')
        end_str_civil = end_date.strftime('%Y-%m-%dT23:59:59')
        date_start = start_date.strftime('%Y-%m-%d')
        date_end_plus_1 = (end_date + timedelta(days=1)).strftime('%Y-%m-%d')

        if collection_type == 'sleep':
            parent = 'users/me/dataTypes/sleep'
            filter_expr = f'sleep.interval.end_time >= "{start_str_rfc}" AND sleep.interval.end_time < "{end_str_rfc}"'
        elif collection_type == 'exercise':
            parent = 'users/me/dataTypes/exercise'
            filter_expr = f'exercise.interval.civil_start_time >= "{start_str_civil}" AND exercise.interval.civil_start_time < "{end_str_civil}"'
        elif collection_type == 'hrv':
            parent = 'users/me/dataTypes/daily-heart-rate-variability'
            filter_expr = f'daily_heart_rate_variability.date >= "{date_start}" AND daily_heart_rate_variability.date < "{date_end_plus_1}"'
        elif collection_type == 'weight':
            parent = 'users/me/dataTypes/weight'
            filter_expr = f'weight.sample_time.physical_time >= "{start_str_rfc}" AND weight.sample_time.physical_time < "{end_str_rfc}"'
        elif collection_type == 'resting_heart_rate':
            parent = 'users/me/dataTypes/daily-resting-heart-rate'
            filter_expr = f'daily_resting_heart_rate.date >= "{date_start}" AND daily_resting_heart_rate.date < "{date_end_plus_1}"'
        elif collection_type == 'breathing_rate':
            parent = 'users/me/dataTypes/respiratory-rate-sleep-summary'
            filter_expr = f'respiratory_rate_sleep_summary.sample_time.physical_time >= "{start_str_rfc}" AND respiratory_rate_sleep_summary.sample_time.physical_time < "{end_str_rfc}"'
        elif collection_type == 'intraday_heart_rate':
            parent = 'users/me/dataTypes/heart-rate'
            filter_expr = f'heart_rate.sample_time.physical_time >= "{start_str_rfc}" AND heart_rate.sample_time.physical_time < "{end_str_rfc}"'
        else:
            return None, None

        return parent, filter_expr

    def fetch_and_process(self,
                          collection_type: str,
                          start_date: datetime,
                          end_date: datetime,
                          is_webhook: bool = False):
        """
        Fetches sessions from the Google Health Rest API for a given date range and processes them.
        """
        if collection_type == 'intraday_heart_rate':
            # rollUp has a 14-day limit for heart-rate
            max_days = 14
            current_start = start_date
            while current_start <= end_date:
                current_end = min(current_start + timedelta(days=max_days), end_date)
                self._fetch_and_process_chunk(collection_type, current_start, current_end)
                current_start = current_end
                if current_start == end_date:
                    break
        else:
            self._fetch_and_process_chunk(collection_type, start_date, end_date)

    def _fetch_and_process_chunk(self, collection_type: str, start_date: datetime, end_date: datetime):
        parent, filter_expr = self.get_query_params(collection_type, start_date, end_date)
        if not parent:
            log.warning(f"No specific handler yet for live sync of collection: {collection_type}")
            return

        # Prepare strings for rollUp range if needed
        start_str_rfc = start_date.strftime('%Y-%m-%dT00:00:00.000Z')
        end_str_rfc = end_date.strftime('%Y-%m-%dT23:59:59.999Z')

        log.info(f"Fetching Google Health {collection_type} from {start_date} to {end_date}")

        try:
            points = []
            page_token = None
            while True:
                # Default pageSize for dataPoints is 1440, but max is 10000
                # except for exercise/sleep which is capped at 25.
                page_size = 10000
                if collection_type in ['exercise', 'sleep']:
                    page_size = 25

                if collection_type == 'intraday_heart_rate':
                    # Use rollUp for 1 minute resolution instead of 1 second raw points
                    body = {
                        "windowSize": "60s",
                        "range": {
                            "startTime": start_str_rfc,
                            "endTime": end_str_rfc
                        },
                        "pageSize": page_size,
                        "pageToken": page_token
                    }
                    response = self.service.users().dataTypes().dataPoints().rollUp(parent=parent, body=body).execute()
                    new_points = response.get('rollupDataPoints', [])
                else:
                    response = self.service.users().dataTypes().dataPoints().list(parent=parent,
                                                                                  filter=filter_expr,
                                                                                  pageToken=page_token,
                                                                                  pageSize=page_size).execute()
                    new_points = response.get('dataPoints', [])

                points.extend(new_points)

                page_token = response.get('nextPageToken')
                if not page_token:
                    break

            log.info(f"Retrieved {len(points)} {collection_type} records from Google Health.")
            self.mapper.process_data_points_by_type(collection_type, points)

        except Exception as e:
            log.error(f"Error fetching Google Health data chunk {collection_type}: {e}", exc_info=True)
            raise

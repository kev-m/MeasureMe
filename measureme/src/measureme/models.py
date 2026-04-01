"""
Database models for MeasureMe.

This module defines the explicit, decoupled tables used to store user health data.
By avoiding inheritance, it improves query performance and provides explicit primary 
key logic linking directly to globally unique external identifiers.
"""
import json
from typing import Any, Dict, AnyStr
from sqlalchemy import Column, Integer, BigInteger, Float, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class SleepSession(Base):
    """Represents a single, discrete sleep event (e.g. a night's sleep or a nap).

    Philosophy:
        Each row corresponds to one sleep log as reported by the vendor. The primary
        key ``global_id`` is the vendor-native log identifier (e.g. Fitbit's integer
        ``logId`` field returned by the Sleep API or present in a Takeout export). Because
        Fitbit guarantees these IDs are globally unique across all users and time, no
        surrogate key is required. Ingestors for other vendors must map whatever
        equivalent unique identifier that vendor exposes (e.g. a UUID, a composite
        date-string, etc.) to ``global_id`` — if the vendor provides no such identifier,
        a deterministic hash (e.g. SHA-1 of ``user_id + start_time``) is acceptable.

    Duration vs. time in bed:
        ``duration_minutes`` reflects the total *sleep* duration as reported by the
        vendor (i.e. deep + light + REM + awake minutes). ``time_in_bed_minutes`` is the
        broader window from when the user got into bed to when they got out, and will
        typically be larger. If a vendor does not distinguish between the two, populate
        ``duration_minutes`` and leave ``time_in_bed_minutes`` null.

    Sleep stages:
        ``deep_sleep_minutes``, ``light_sleep_minutes``, ``rem_sleep_minutes``, and
        ``awake_minutes`` should sum to ``duration_minutes``. If the vendor does not
        report granular stages (e.g. it only reports a single total), leave the stage
        columns null and populate only ``duration_minutes``.

    Ingestor guidance:
        - Fitbit Takeout: parse ``sleep-YYYY-MM-DD.json``; each element in the ``sleep``
          array is one ``SleepSession``. The ``logId`` key maps to ``global_id``.
        - Fitbit Webhook/API: ``POST /1.2/user/-/sleep/list`` response; same ``logId``
          field.
        - Other vendors: map the closest equivalent unique sleep-log identifier to
          ``global_id``, normalise all stage durations to minutes, and set
          ``is_main_sleep = 1`` for the primary overnight sleep per calendar day.
    """
    __tablename__ = 'sleep_session'
    global_id = Column(BigInteger, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    source_id = Column(Integer, nullable=False)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, nullable=False)

    is_main_sleep = Column(Integer, nullable=True)

    deep_sleep_minutes = Column(Integer, nullable=True)
    light_sleep_minutes = Column(Integer, nullable=True)
    rem_sleep_minutes = Column(Integer, nullable=True)

    awake_minutes = Column(Integer, nullable=True)
    time_in_bed_minutes = Column(Integer, nullable=True)
    efficiency_score = Column(Integer, nullable=True)

    timezone = Column(String(50), nullable=True, default='Europe/London')
    metadata_json = Column(Text)

    def get_metadata(self) -> Dict[str, Any]:
        if self.metadata_json:
            try: return json.loads(self.metadata_json)
            except json.JSONDecodeError: pass
        return {}

class ExerciseSession(Base):
    """Represents a single, discrete physical activity or workout event.

    Philosophy:
        Each row corresponds to one exercise log as reported by the vendor. As with
        ``SleepSession``, the primary key ``global_id`` is the vendor-native activity
        log identifier (e.g. Fitbit's ``logId`` from the Activities API). Fitbit uses
        64-bit integers here, which are globally unique across all activity types and
        users. Ingestors for other vendors should follow the same ``global_id`` mapping
        strategy described in ``SleepSession``.

    Activity classification:
        ``activity_name`` should be the human-readable activity label as the vendor
        reports it (e.g. ``'Walk'``, ``'Run'``, ``'Cycling'``). Do not normalise or
        translate vendor names — store the raw label so that downstream analysis can
        group or filter as needed without losing vendor fidelity.

    Optional metrics:
        ``steps``, ``calories_burned``, ``distance_km``, and ``average_heart_rate`` are
        all nullable because not every activity type or vendor reports all of them (e.g.
        a swimming session may not have steps). Populate whatever the vendor provides
        and leave the rest null.

    Ingestor guidance:
        - Fitbit Takeout: parse ``exercise-YYYY-MM-DD.json``; each element is one
          ``ExerciseSession``. The ``logId`` key maps to ``global_id``. The
          ``activitiesExercise`` array also contains ``activityName``, ``steps``,
          ``calories``, ``distance``, and ``averageHeartRate``.
        - Fitbit Webhook/API: ``GET /1/user/-/activities/list`` response.
        - Other vendors: map the closest unique activity-log identifier to ``global_id``
          and normalise distance to kilometres before storing in ``distance_km``.
    """
    __tablename__ = 'exercise_session'
    global_id = Column(BigInteger, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    source_id = Column(Integer, nullable=False)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    timezone = Column(String(50), nullable=True, default='Europe/London')

    activity_name = Column(String(100), nullable=True)
    duration_seconds = Column(Integer, nullable=False)
    steps = Column(Integer, nullable=True)
    calories_burned = Column(Float, nullable=True)
    distance_km = Column(Float, nullable=True)
    average_heart_rate = Column(Integer, nullable=True)

    metadata_json = Column(Text)

    def get_metadata(self) -> Dict[str, Any]:
        if self.metadata_json:
            try: return json.loads(self.metadata_json)
            except json.JSONDecodeError: pass
        return {}

class HealthMetric(Base):
    """Represents a single scalar health measurement associated with a calendar day.

    Philosophy:
        Unlike ``SleepSession`` and ``ExerciseSession``, a ``HealthMetric`` is a
        *daily summary* value rather than an event with a start and end time. Examples
        include resting heart rate (one value per day), HRV (one RMSSD value per
        overnight measurement window), breathing rate, weight, SpO2, and similar.
        The table is intentionally generic — the ``metric_type`` string distinguishes
        what is being measured rather than a separate table per metric.

    Primary key:
        Because daily metrics often have no natural vendor-assigned unique ID, a
        surrogate auto-increment ``metric_id`` is used as the primary key. The optional
        ``global_id`` column can be populated with a vendor log identifier *if one
        exists* (some Fitbit endpoints do return IDs for certain metrics), and also
        serves as a deduplication guard during re-ingestion.

    Metric types (canonical names):
        Ingestors must map vendor-specific field names to the following canonical
        ``metric_type`` strings to ensure cross-vendor compatibility:

        - ``'resting_heart_rate'``  — daily resting HR in bpm.
        - ``'hrv_rmssd'``           — overnight HRV (RMSSD) in milliseconds.
        - ``'breathing_rate'``      — nightly average breathing rate in breaths/min.
        - ``'spo2_avg'``            — average overnight SpO2 percentage.
        - ``'weight'``              — body weight.
        - ``'steps'``               — total daily step count (dimensionless count).

        New ingestors should reuse these names where applicable and introduce new
        lower_snake_case names only when there is genuinely no existing equivalent.
    
    Unit:
        Ingestors should populate the unit appropriately to one of the following
        canonical ``unit`` strings:

        - ``'bpm'``                 — Heart-rate beats per minute.
        - ``'breaths/min'``         — Breathing rate, breaths per minute.
        - ``'ms'``                  — SI speed, metres per second.
        - ``'kg'``                  — SI weight in kilograms.
        - ``'index'``               — Non-dimensional index.
        
    Timestamp:
        ``timestamp`` should be set to midnight (00:00:00) of the calendar day the
        measurement represents, in the user's local timezone. Use the ``timezone``
        column to record the IANA timezone string (e.g. ``'Europe/London'``).

    Ingestor guidance:
        - Fitbit Takeout: daily summary files such as ``resting_heart_rate-YYYY-MM-DD.json``
          and ``heart_rate_variability_details-YYYY-MM-DD.json`` map directly to rows here.
        - Fitbit API: endpoints such as ``/1/user/-/hr/date/{date}.json`` and
          ``/1/user/-/hrv/date/{date}.json`` provide the source values.
        - Other vendors: normalise all units to the SI/canonical units listed above
          before inserting. When a vendor provides a daily summary with multiple metrics
          in one response, insert one row per ``metric_type``.
    """
    __tablename__ = 'health_metric'
    metric_id = Column(Integer, primary_key=True, autoincrement=True)
    global_id = Column(BigInteger, unique=True, index=True, nullable=True)
    user_id = Column(Integer, nullable=False, index=True)
    source_id = Column(Integer, nullable=False)
    metric_type = Column(String(50), nullable=False, index=True)
    value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    timezone = Column(String(50), nullable=True, default='Europe/London')

class IntradayMetricType(Base):
    """Lookup table defining the integer enum values used by ``HealthIntraday.metric_type_id``.

    Philosophy:
        Rather than scattering magic integer constants across ingestors, this table
        provides a single authoritative registry. Each row maps a stable numeric
        ``id`` to a canonical ``short_name`` and a human-readable ``description``.
        The ``id`` values are fixed and must never be renumbered — if a new metric
        is added, assign the next available integer.

    Seeding:
        The table is populated once at database initialisation time via
        ``Base.metadata.create_all`` followed by a seed insert (see
        ``measureme.db.seed_intraday_metric_types``). Ingestors must not insert
        into this table; they should only read from it (or use the constants
        defined in ``measureme.constants.IntradayMetric``).

    Canonical values:
        - 1 / ``heart_rate``          — instantaneous heart rate in bpm.
        - 2 / ``steps``               — step count over the preceding interval.
        - 3 / ``spo2``               — blood oxygen saturation (%).
        - 4 / ``skin_temp_deviation`` — skin temperature deviation from baseline (°C).
    """
    __tablename__ = 'intraday_metric_type'

    id          = Column(Integer, primary_key=True)          # stable enum value
    short_name  = Column(String(50), nullable=False, unique=True)
    description = Column(String(200), nullable=False)


INTRADAY_METRIC_TYPE_SEED = [
    {'id': 1, 'short_name': 'heart_rate',          'description': 'Instantaneous heart rate in beats per minute (bpm).'},
    {'id': 2, 'short_name': 'steps',               'description': 'Step count accumulated over the preceding 60-second interval.'},
    {'id': 3, 'short_name': 'spo2',                'description': 'Blood oxygen saturation percentage (SpO2).'},
    {'id': 4, 'short_name': 'skin_temp_deviation', 'description': 'Skin temperature deviation from the user\'s personal baseline in °C.'},
]
"""Seed rows for ``IntradayMetricType``. Pass to ``db.execute(insert(IntradayMetricType), ...)``
at initialisation time using ``INSERT OR IGNORE`` semantics so re-runs are idempotent."""

def MetricTypeFromString(short_name: AnyStr):
    """Retrieve the ID of the provided metric type, from string."""
    return next((row['id'] for row in INTRADAY_METRIC_TYPE_SEED if row['short_name'] == short_name), None)

class HealthIntraday(Base):
    """Represents a single high-frequency telemetry sample (e.g. heart rate every 60 s).

    Philosophy:
        This table is designed for *intraday* time-series data — measurements recorded
        multiple times per day at a fixed cadence. The composite primary key
        ``(timestamp_utc, user_id, metric_type_id)`` eliminates the need for a surrogate
        key and naturally deduplicates re-ingested samples. ``timestamp_utc`` is stored
        as a Unix epoch integer (seconds since 1970-01-01T00:00:00Z) for compact storage
        and efficient range queries without timezone conversion.

    metric_type_id:
        This is an integer enum that maps to a specific telemetry stream. Ingestors must
        agree on the mapping before inserting data. Recommended values:

        - ``1`` — heart rate (bpm), 60-second granularity.
        - ``2`` — steps (count), 60-second granularity.
        - ``3`` — SpO2 (%), 60-second granularity.
        - ``4`` — skin temperature deviation (°C), 60-second granularity.

        This list should be extended in a shared constants module rather than hardcoded
        in individual ingestors.

    session_id:
        Optional foreign reference to the ``global_id`` of the parent ``SleepSession``
        or ``ExerciseSession`` that this sample belongs to. Because both session tables
        share the same ``global_id`` namespace (Fitbit guarantees no collision between
        sleep and activity log IDs), a single ``session_id`` column is sufficient.
        Leave null for samples that are not associated with a specific session (e.g.
        continuous daytime heart rate).

    Ingestor guidance:
        - Fitbit API: ``GET /1/user/-/activities/heart/date/{date}/1d/1min.json``
          returns 1-minute HR samples. Convert the ``time`` field to a UTC Unix
          timestamp before inserting.
        - Fitbit Takeout: ``heart_rate-YYYY-MM-DD.json`` contains the same data in
          an offline export.
        - Other vendors: always normalise timestamps to UTC Unix seconds. Choose the
          appropriate ``metric_type_id`` from the enum above, or extend it.
    """
    __tablename__ = 'health_intraday'
    timestamp_utc = Column(Integer, primary_key=True)
    user_id = Column(Integer, primary_key=True)
    metric_type_id = Column(Integer, ForeignKey('intraday_metric_type.id'), primary_key=True, nullable=False, comment='ForeignKey to IntradayMetricType.id')
    __table_args__ = (
        {'sqlite_autoincrement': False},
    )
    __mapper_args__ = {}
    value = Column(Float, nullable=False)
    session_id = Column(BigInteger, nullable=True, index=True)
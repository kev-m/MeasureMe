import json
from datetime import datetime, timedelta
from measureme.models import HealthMetric, SleepSession, ExerciseSession, HealthIntraday, IntradayMetricType

def test_health_metric_insertion(db_session):
    metric = HealthMetric(
        user_id=1,
        source_id=2,
        timestamp=datetime(2026, 3, 21, 8, 0, 0),
        metric_type='resting_heart_rate',
        value=65.5,
        unit='bpm'
    )
    db_session.add(metric)
    db_session.commit()

    retrieved = db_session.query(HealthMetric).filter_by(metric_type='resting_heart_rate').first()
    assert retrieved is not None
    assert retrieved.value == 65.5
    assert retrieved.unit == 'bpm'
    assert retrieved.user_id == 1

def test_sleep_session_with_metadata(db_session):
    start_time = datetime(2026, 3, 21, 6, 0, 0)
    end_time = start_time + timedelta(hours=8)
    session_data = SleepSession(
        global_id=12345,
        user_id=1,
        source_id=2,
        start_time=start_time,
        end_time=end_time,
        duration_seconds=int((end_time - start_time).total_seconds()),
        metadata_json=json.dumps({'stages': {'deep': 60, 'light': 180, 'rem': 90}})
    )
    db_session.add(session_data)
    db_session.commit()

    retrieved = db_session.query(SleepSession).filter_by(global_id=12345).first()
    assert retrieved is not None
    assert retrieved.duration_seconds == 8 * 3600
    metadata = retrieved.get_metadata()
    assert 'stages' in metadata
    assert metadata['stages']['rem'] == 90

def test_exercise_session(db_session):
    start_time = datetime(2026, 3, 21, 10, 0, 0)
    end_time = start_time + timedelta(hours=1)
    session_data = ExerciseSession(
        global_id=54321,
        user_id=1,
        source_id=2,
        start_time=start_time,
        end_time=end_time,
        duration_seconds=3600,
        activity_name="Run",
        steps=5000
    )
    db_session.add(session_data)
    db_session.commit()

    retrieved = db_session.query(ExerciseSession).filter_by(global_id=54321).first()
    assert retrieved is not None
    assert retrieved.duration_seconds == 3600
    assert retrieved.activity_name == "Run"
    assert retrieved.steps == 5000

def test_health_intraday_data(db_session):
    intraday = HealthIntraday(
        user_id=1,
        timestamp_utc=1710990000,
        metric_type_id=1,
        value=72.5
    )
    db_session.add(intraday)
    db_session.commit()

    retrieved = db_session.query(HealthIntraday).filter_by(metric_type_id=1).first()
    assert retrieved is not None
    assert retrieved.value == 72.5
    assert retrieved.timestamp_utc == 1710990000

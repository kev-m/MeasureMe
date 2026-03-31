from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import SleepSession, ExerciseSession, HealthMetric, HealthIntraday, IntradayMetricType

class MeasureMeQuery:
    """
    A high-level abstraction for querying the MeasureMe database without needing 
    to interact directly with SQLAlchemy.
    """
    def __init__(self, session: Session):
        self.session = session

    # -------------------------------------------------------------------------
    # 1. Introspection / Discovery Queries
    # -------------------------------------------------------------------------
    def get_available_session_types(self, user_id: Optional[int] = None) -> List[str]:
        types = []
        q_sleep = self.session.query(SleepSession)
        if user_id is not None: q_sleep = q_sleep.filter(SleepSession.user_id == user_id)
        if q_sleep.first() is not None: types.append("sleep")

        q_exercise = self.session.query(ExerciseSession)
        if user_id is not None: q_exercise = q_exercise.filter(ExerciseSession.user_id == user_id)
        if q_exercise.first() is not None: types.append("exercise")
            
        return types

    def get_available_metric_types(self, user_id: Optional[int] = None) -> List[str]:
        """Returns a list of all distinct daily health metric types available in the database (e.g., 'resting_heart_rate')."""
        query = self.session.query(HealthMetric.metric_type).distinct()
        if user_id is not None:
            query = query.filter(HealthMetric.user_id == user_id)
        return [row[0] for row in query.all()]

    def get_available_intraday_types(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Returns a list of all distinct high-frequency intraday metric types available, including id, short_name, and description."""
        
        # Get IDs that actually have data
        data_query = self.session.query(HealthIntraday.metric_type_id).distinct()
        if user_id is not None:
            data_query = data_query.filter(HealthIntraday.user_id == user_id)
        
        active_ids = [row[0] for row in data_query.all()]
        
        if not active_ids:
            return []
            
        # Join with IntradayMetricType to get the names
        # Assuming the table IntradayMetricType is correctly seeded in the DB
        metrics_query = self.session.query(IntradayMetricType).filter(IntradayMetricType.id.in_(active_ids))
        
        results = []
        for m in metrics_query.all():
            results.append({
                "id": m.id,
                "short_name": m.short_name,
                "description": m.description
            })
            
        return results

    def get_date_bounds(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Returns the earliest and latest local dates recorded in the sessions and metrics tables.
        Useful for building calendar bounds in the UI.
        """
        q_min_metric = self.session.query(func.min(HealthMetric.timestamp))
        q_max_metric = self.session.query(func.max(HealthMetric.timestamp))
        q_min_sleep = self.session.query(func.min(SleepSession.start_time))
        q_max_sleep = self.session.query(func.max(SleepSession.end_time))
        q_min_ex = self.session.query(func.min(ExerciseSession.start_time))
        q_max_ex = self.session.query(func.max(ExerciseSession.end_time))
        
        if user_id is not None:
            q_min_metric = q_min_metric.filter(HealthMetric.user_id == user_id)
            q_max_metric = q_max_metric.filter(HealthMetric.user_id == user_id)
            q_min_sleep = q_min_sleep.filter(SleepSession.user_id == user_id)
            q_max_sleep = q_max_sleep.filter(SleepSession.user_id == user_id)
            q_min_ex = q_min_ex.filter(ExerciseSession.user_id == user_id)
            q_max_ex = q_max_ex.filter(ExerciseSession.user_id == user_id)
            
        min_m = q_min_metric.scalar()
        max_m = q_max_metric.scalar()
        min_sl = q_min_sleep.scalar()
        max_sl = q_max_sleep.scalar()
        min_ex = q_min_ex.scalar()
        max_ex = q_max_ex.scalar()

        all_mins = [d for d in [min_m, min_sl, min_ex] if d is not None]
        all_maxs = [d for d in [max_m, max_sl, max_ex] if d is not None]

        return {
            "first_record": min(all_mins) if all_mins else None,
            "last_record": max(all_maxs) if all_maxs else None
        }

    # -------------------------------------------------------------------------
    # 2. Data Retrieval Queries
    # -------------------------------------------------------------------------
    def get_sessions(
        self,
        session_type: str,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[int] = None,
        limit: Optional[int] = 100,
        order_by_desc: bool = True
    ) -> List[Any]:
        if session_type == "sleep":
            model = SleepSession
            filter_time = SleepSession.end_time
        elif session_type == "exercise":
            model = ExerciseSession
            filter_time = ExerciseSession.start_time
        else:
            return []

        query = self.session.query(model).filter(filter_time >= start_date).filter(filter_time <= end_date)

        if user_id is not None:
            query = query.filter(model.user_id == user_id)

        if order_by_desc:
            query = query.order_by(model.start_time.desc())
        else:
            query = query.order_by(model.start_time.asc())

        if limit is not None:
            query = query.limit(limit)

        return query.all()

    def get_daily_metrics(
        self,
        metric_type: str,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[int] = None,
        limit: Optional[int] = 100,
        order_by_desc: bool = True
    ) -> List[HealthMetric]:
        """Retrieves summary health metrics (like weight or resting HR) matching the criteria."""
        query = self.session.query(HealthMetric)\
            .filter(HealthMetric.metric_type == metric_type)\
            .filter(HealthMetric.timestamp >= start_date)\
            .filter(HealthMetric.timestamp <= end_date)

        if user_id is not None:
            query = query.filter(HealthMetric.user_id == user_id)

        if order_by_desc:
            query = query.order_by(HealthMetric.timestamp.desc())
        else:
            query = query.order_by(HealthMetric.timestamp.asc())
            
        if limit is not None:
            query = query.limit(limit)

        return query.all()

    def get_intraday_telemetry(
        self,
        metric_type_id: int,
        start_timestamp_utc: int,
        end_timestamp_utc: int,
        user_id: Optional[int] = None,
        limit: Optional[int] = 100,
        order_by_desc: bool = True

    ) -> List[HealthIntraday]:
        """
        Retrieves high-frequency telemetry (like 60-second HR) matching the UTC boundaries.
        Returns them sorted chronologically (ascending).
        """
        query = self.session.query(HealthIntraday)\
            .filter(HealthIntraday.metric_type_id == metric_type_id)\
            .filter(HealthIntraday.timestamp_utc >= start_timestamp_utc)\
            .filter(HealthIntraday.timestamp_utc <= end_timestamp_utc)
            
        if user_id is not None:
            query = query.filter(HealthIntraday.user_id == user_id)

        if order_by_desc:
            query = query.order_by(HealthIntraday.timestamp_utc.desc())
        else:
            query = query.order_by(HealthIntraday.timestamp_utc.asc())

        if limit is not None:
            query = query.limit(limit)

        return query.all()

    def get_relaxation_data(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[int] = None,
        limit: Optional[int] = 100,
        order_by_desc: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Gathers sleep session data and correlates it with daily metrics (BR, HRV, RHR)
        for a unified relaxation dashboard.
        """
        from .models import SleepSession

        # Get sleep sessions
        q_sleep = self.session.query(SleepSession)\
            .filter(SleepSession.start_time >= start_date)\
            .filter(SleepSession.start_time <= end_date)

        if user_id is not None:
            q_sleep = q_sleep.filter(SleepSession.user_id == user_id)

        if order_by_desc:
            q_sleep = q_sleep.order_by(SleepSession.start_time.desc())
        else:
            q_sleep = q_sleep.order_by(SleepSession.start_time.asc())

        if limit is not None:
            q_sleep = q_sleep.limit(limit)

        sleep_sessions = q_sleep.all()

        # Gather relevant daily metrics within the date range
        # We index them by (date, metric_type) for O(1) correlation
        q_metrics = self.session.query(HealthMetric)\
            .filter(HealthMetric.metric_type.in_(["breathing_rate", "hrv_rmssd", "resting_heart_rate"]))\
            .filter(HealthMetric.timestamp >= start_date)\
            .filter(HealthMetric.timestamp <= end_date)

        if user_id is not None:
            q_metrics = q_metrics.filter(HealthMetric.user_id == user_id)

        all_metrics = q_metrics.all()

        metrics_by_date = {}
        for m in all_metrics:
            d_str = m.timestamp.date().isoformat()
            if d_str not in metrics_by_date:
                metrics_by_date[d_str] = {}
            metrics_by_date[d_str][m.metric_type] = m.value

        # Build combined data structure
        results = []
        for s in sleep_sessions:
            if s.is_main_sleep != 1:
                continue
            # According to common tracker logic, the "sleep date" usually corresponds to the end date 
            # (waking up), or the date the log covers. We'll use the end_time date to correlate with metrics.
            d_str = s.end_time.date().isoformat()
            day_metrics = metrics_by_date.get(d_str, {})

            hours = s.duration_seconds / 3600.0 if s.duration_seconds else None
            
            # Calculate % deep sleep
            pct_deep = None
            if s.deep_sleep_seconds is not None and s.duration_seconds:
                pct_deep = s.deep_sleep_seconds / (s.duration_seconds + s.awake_seconds)

            results.append({
                "date": d_str,
                "sleep_hours": hours,
                "deep_sleep_pct": pct_deep,
                "sleep_score": s.efficiency_score,
                "br": day_metrics.get("breathing_rate"),
                "hrv": day_metrics.get("hrv_rmssd"),
                "rhr": day_metrics.get("resting_heart_rate")
            })

        return results


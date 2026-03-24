from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import HealthSession, HealthMetric, HealthIntraday

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
        """Returns a list of all distinct session types available in the database (e.g., 'sleep', 'exercise')."""
        query = self.session.query(HealthSession.session_type).distinct()
        if user_id is not None:
            query = query.filter(HealthSession.user_id == user_id)
        return [row[0] for row in query.all()]

    def get_available_metric_types(self, user_id: Optional[int] = None) -> List[str]:
        """Returns a list of all distinct daily health metric types available in the database (e.g., 'resting_heart_rate')."""
        query = self.session.query(HealthMetric.metric_type).distinct()
        if user_id is not None:
            query = query.filter(HealthMetric.user_id == user_id)
        return [row[0] for row in query.all()]

    def get_available_intraday_types(self, user_id: Optional[int] = None) -> List[int]:
        """Returns a list of all distinct high-frequency intraday metric IDs available."""
        query = self.session.query(HealthIntraday.metric_type_id).distinct()
        if user_id is not None:
            query = query.filter(HealthIntraday.user_id == user_id)
        return [row[0] for row in query.all()]

    def get_date_bounds(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Returns the earliest and latest local dates recorded in the sessions and metrics tables.
        Useful for building calendar bounds in the UI.
        """
        q_min_metric = self.session.query(func.min(HealthMetric.timestamp))
        q_max_metric = self.session.query(func.max(HealthMetric.timestamp))
        q_min_session = self.session.query(func.min(HealthSession.start_time))
        q_max_session = self.session.query(func.max(HealthSession.end_time))
        
        if user_id is not None:
            q_min_metric = q_min_metric.filter(HealthMetric.user_id == user_id)
            q_max_metric = q_max_metric.filter(HealthMetric.user_id == user_id)
            q_min_session = q_min_session.filter(HealthSession.user_id == user_id)
            q_max_session = q_max_session.filter(HealthSession.user_id == user_id)

        min_m = q_min_metric.scalar()
        max_m = q_max_metric.scalar()
        min_s = q_min_session.scalar()
        max_s = q_max_session.scalar()

        all_mins = [d for d in [min_m, min_s] if d is not None]
        all_maxs = [d for d in [max_m, max_s] if d is not None]

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
        limit: Optional[int] = None,
        order_by_desc: bool = True
    ) -> List[HealthSession]:
        """Retrieves health sessions (like sleep or exercise) matching the criteria."""
        query = self.session.query(HealthSession)\
            .filter(HealthSession.session_type == session_type)\
            .filter(HealthSession.start_time >= start_date)\
            .filter(HealthSession.start_time <= end_date)
            
        if user_id is not None:
            query = query.filter(HealthSession.user_id == user_id)
            
        if order_by_desc:
            query = query.order_by(HealthSession.start_time.desc())
        else:
            query = query.order_by(HealthSession.start_time.asc())
            
        if limit is not None:
            query = query.limit(limit)
            
        return query.all()

    def get_daily_metrics(
        self,
        metric_type: str,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[int] = None,
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
            
        return query.all()

    def get_intraday_telemetry(
        self,
        metric_type_id: int,
        start_timestamp_utc: int,
        end_timestamp_utc: int,
        user_id: Optional[int] = None
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
            
        return query.order_by(HealthIntraday.timestamp_utc.asc()).all()

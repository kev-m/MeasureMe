import json
from datetime import datetime
from typing import Optional, Any, Dict
from sqlalchemy import Column, Integer, Float, String, DateTime, Text, Index
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class HealthSession(Base):
    """
    Represents a high-level activity or sleep event.
    """
    __tablename__ = 'health_session'

    session_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    source_id = Column(Integer, nullable=False)
    session_type = Column(String(50), nullable=False)  # e.g., 'sleep', 'workout', 'meditation'
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    duration_seconds = Column(Integer, nullable=False)
    timezone = Column(String(50), nullable=True, default="Europe/London")
    metadata_json = Column(Text)  # Raw JSON string of vendor-specific attributes.

    def get_metadata(self) -> Dict[str, Any]:
        """Parses the metadata_json string into a Python dictionary."""
        if self.metadata_json:
            try:
                return json.loads(self.metadata_json)
            except json.JSONDecodeError:
                pass
        return {}


class HealthMetric(Base):
    """
    Represents a discrete health measurement or daily summary metric.
    """
    __tablename__ = 'health_metric'

    metric_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    source_id = Column(Integer, nullable=False)
    metric_type = Column(String(50), nullable=False, index=True) # e.g., 'heart_rate_avg', 'steps'
    value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False) # e.g., 'bpm', 'count', 'percent'
    timestamp = Column(DateTime, nullable=False, index=True)
    timezone = Column(String(50), nullable=True, default="Europe/London")
    
    __table_args__ = (
        Index('idx_health_metric_user_type_time', 'user_id', 'metric_type', 'timestamp'),
    )


class HealthIntraday(Base):
    """
    Represents high-frequency telemetry data.
    Note: For true WITHOUT ROWID in SQLite, further table arg configuration is required,
    but this provides the standard SQLAlchemy compatibility for both MariaDB and SQLite.
    """
    __tablename__ = 'health_intraday'

    # Using a composite primary key to mimic WITHOUT ROWID logic's efficiency
    timestamp_utc = Column(Integer, primary_key=True)
    user_id = Column(Integer, primary_key=True)
    metric_type_id = Column(Integer, primary_key=True)
    
    value = Column(Float, nullable=False)
    session_id = Column(Integer, nullable=True, index=True)

    __table_args__ = (
        # Adding sqlite_autoincrement=False just ensures we don't accidentally get an implicit rowid if we manipulate the DDL manually later
        {'sqlite_autoincrement': False}
    )

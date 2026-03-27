import os
import json
from datetime import datetime, timedelta, date
from flask import Blueprint, request, jsonify
from dotenv import load_dotenv
from measureme.query import MeasureMeQuery
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

load_dotenv()

measureme_api_bp = Blueprint('measureme_api', __name__, url_prefix='/api/v1/measureme')

default_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../MeasureMe/measureme.db'))
MEASUREME_DB = os.environ.get('MEASUREME_DB', f'sqlite:///{default_db_path}')

engine = create_engine(
    MEASUREME_DB,
    poolclass=NullPool,
    connect_args={'timeout': 15}
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA query_only=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def serialize_model(model):
    """Converts a SQLAlchemy model instance into a dictionary."""
    if isinstance(model, dict):
        return {k: serialize_model(v) for k, v in model.items()}
    if hasattr(model, '__table__'):
        result = {}
        for c in model.__table__.columns:
            val = getattr(model, c.name)
            if isinstance(val, (datetime, date)):
                result[c.name] = val.isoformat()
            else:
                result[c.name] = val
        return result
    if isinstance(model, (datetime, date)):
        return model.isoformat()
    return model

def parse_date_args(bounds, args):
    end_date_str = args.get('end_date')
    start_date_str = args.get('start_date')

    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        end_date = end_date.replace(hour=23, minute=59, second=59)
    else:
        end_date = bounds['last_record'] or datetime.utcnow()

    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    else:
        start_date = bounds['first_record'] if end_date_str else (end_date - timedelta(days=30))
    
    return start_date, end_date

@measureme_api_bp.route('/types/sessions', methods=['GET'])
def get_session_types():
    db = SessionLocal()
    try:
        user_id = request.args.get('user_id', type=int)
        query = MeasureMeQuery(db)
        return jsonify(query.get_available_session_types(user_id=user_id))
    finally:
        db.close()

@measureme_api_bp.route('/types/metrics', methods=['GET'])
def get_metric_types():
    db = SessionLocal()
    try:
        user_id = request.args.get('user_id', type=int)
        query = MeasureMeQuery(db)
        return jsonify(query.get_available_metric_types(user_id=user_id))
    finally:
        db.close()

@measureme_api_bp.route('/types/intraday', methods=['GET'])
def get_intraday_types():
    db = SessionLocal()
    try:
        user_id = request.args.get('user_id', type=int)
        query = MeasureMeQuery(db)
        return jsonify(query.get_available_intraday_types(user_id=user_id))
    finally:
        db.close()

@measureme_api_bp.route('/bounds', methods=['GET'])
def get_bounds():
    db = SessionLocal()
    try:
        user_id = request.args.get('user_id', type=int)
        query = MeasureMeQuery(db)
        bounds = query.get_date_bounds(user_id=user_id)
        # Convert datetime to isoformat if present
        return jsonify({k: (serialize_model(v) if v else None) for k, v in bounds.items()})
    finally:
        db.close()

@measureme_api_bp.route('/sessions/<session_type>', methods=['GET'])
def get_sessions(session_type):
    db = SessionLocal()
    try:
        query = MeasureMeQuery(db)
        user_id = request.args.get('user_id', type=int)
        limit = request.args.get('limit', default=100, type=int)
        order_desc = request.args.get('order_desc', default='true').lower() == 'true'
        
        bounds = query.get_date_bounds(user_id=user_id)
        start_date, end_date = parse_date_args(bounds, request.args)

        sessions = query.get_sessions(
            session_type=session_type,
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            limit=limit,
            order_by_desc=order_desc
        )
        return jsonify([serialize_model(s) for s in sessions])
    finally:
        db.close()

@measureme_api_bp.route('/metrics/<metric_type>', methods=['GET'])
def get_daily_metrics(metric_type):
    db = SessionLocal()
    try:
        query = MeasureMeQuery(db)
        user_id = request.args.get('user_id', type=int)
        limit = request.args.get('limit', default=100, type=int)
        order_desc = request.args.get('order_desc', default='true').lower() == 'true'

        bounds = query.get_date_bounds(user_id=user_id)
        start_date, end_date = parse_date_args(bounds, request.args)

        metrics = query.get_daily_metrics(
            metric_type=metric_type,
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            limit=limit,
            order_by_desc=order_desc
        )
        return jsonify([serialize_model(m) for m in metrics])
    finally:
        db.close()

@measureme_api_bp.route('/intraday/<int:metric_type_id>', methods=['GET'])
def get_intraday_telemetry(metric_type_id):
    db = SessionLocal()
    try:
        query = MeasureMeQuery(db)
        user_id = request.args.get('user_id', type=int)
        
        start_utc = request.args.get('start_timestamp_utc', type=int)
        end_utc = request.args.get('end_timestamp_utc', type=int)
        limit = request.args.get('limit', default=100, type=int)
        order_desc = request.args.get('order_desc', default='true').lower() == 'true'
        
        if start_utc is None or end_utc is None:
            return jsonify({"error": "Missing start_timestamp_utc or end_timestamp_utc"}), 400

        data = query.get_intraday_telemetry(
            metric_type_id=metric_type_id,
            start_timestamp_utc=start_utc,
            end_timestamp_utc=end_utc,
            user_id=user_id,
            limit=limit,
            order_by_desc=order_desc
        )
        return jsonify([serialize_model(d) for d in data])
    finally:
        db.close()

@measureme_api_bp.route('/relaxation', methods=['GET'])
def get_relaxation_data():
    db = SessionLocal()
    try:
        query = MeasureMeQuery(db)
        user_id = request.args.get('user_id', type=int)
        limit = request.args.get('limit', default=100, type=int)
        order_desc = request.args.get('order_desc', default='true').lower() == 'true'

        bounds = query.get_date_bounds(user_id=user_id)
        start_date, end_date = parse_date_args(bounds, request.args)

        results = query.get_relaxation_data(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            limit=limit,
            order_by_desc=order_desc
        )
        return jsonify(results)  # The query returns dicts, no need to serialize models here
    finally:
        db.close()

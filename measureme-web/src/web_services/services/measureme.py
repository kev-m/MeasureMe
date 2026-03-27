import os
import requests
from datetime import datetime, timedelta, date, timezone
import zoneinfo
from flask import Blueprint, render_template, request
from dotenv import load_dotenv

load_dotenv()

measureme_bp = Blueprint('measureme_service', __name__, url_prefix='/measureme')

def get_api_url():
    return request.host_url.rstrip('/') + '/api/v1/measureme'

def dict_to_obj(d):
    if not isinstance(d, dict):
        return d
    class Obj:
        pass
    obj = Obj()
    for k, v in d.items():
        if isinstance(v, str):
            try:
                if 'T' in v:
                    v = datetime.fromisoformat(v)
                elif len(v) == 10 and v.count('-') == 2:
                    v = date.fromisoformat(v)
            except ValueError:
                pass
        elif isinstance(v, dict):
            v = dict_to_obj(v)
        elif isinstance(v, list):
            v = [dict_to_obj(x) if isinstance(x, dict) else x for x in v]
        setattr(obj, k, v)
    return obj

@measureme_bp.route('/', methods=['GET'])
def index():
    api_url = get_api_url()
    user_id = request.args.get('user_id', default=1, type=int)
    
    params = {'user_id': user_id}
    
    session_types = requests.get(f"{api_url}/types/sessions", params=params).json()
    metric_types = requests.get(f"{api_url}/types/metrics", params=params).json()
    intraday_types = requests.get(f"{api_url}/types/intraday", params=params).json()
    
    bounds_resp = requests.get(f"{api_url}/bounds", params=params).json()
    
    # Parse bounds
    first_record_str = bounds_resp.get('first_record')
    last_record_str = bounds_resp.get('last_record')
    first_record = datetime.fromisoformat(first_record_str) if first_record_str else None
    last_record = datetime.fromisoformat(last_record_str) if last_record_str else None
    bounds = (first_record, last_record)
    
    default_end = last_record.strftime('%Y-%m-%d') if last_record else ''
    default_start = (last_record - timedelta(days=7)).strftime('%Y-%m-%d') if last_record else ''

    return render_template(
        'index.html',
        session_types=session_types,
        metric_types=metric_types,
        intraday_types=intraday_types,
        bounds=bounds,
        default_start=default_start,
        default_end=default_end,
        user_id=user_id
    )


def parse_date_args(bounds, args):
    end_date_str = args.get('end_date')
    start_date_str = args.get('start_date')
    
    if end_date_str:
        if 'T' in end_date_str:
            end_date = datetime.fromisoformat(end_date_str)
        else:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            # Preserve time from bounds if it's the exact same day, else run up to EOD
            end_date = end_date.replace(hour=23, minute=59, second=59)
    else:
        end_date = bounds.get('last_record')
        if end_date and isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date)
        elif not end_date:
            end_date = datetime.now()
        
    if start_date_str:
        if 'T' in start_date_str:
            start_date = datetime.fromisoformat(start_date_str)
        else:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    else:
        first_rec = bounds.get('first_record')
        if first_rec and isinstance(first_rec, str):
            first_rec = datetime.fromisoformat(first_rec)
            start_date = first_rec if end_date_str else (end_date - timedelta(days=30))
        elif not first_rec:
            start_date = end_date - timedelta(days=30)
        else:
            start_date = first_rec if end_date_str else (end_date - timedelta(days=30))
        
    return start_date, end_date


@measureme_bp.route('/session/<session_type>', methods=['GET'])
def view_session(session_type):
    api_url = get_api_url()
    user_id = request.args.get('user_id', default=1, type=int)
    
    bounds_resp = requests.get(f"{api_url}/bounds", params={'user_id': user_id}).json()
    start_date, end_date = parse_date_args(bounds_resp, request.args)
    
    params = {
        'user_id': user_id,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'limit': 100,
        'order_desc': 'false'
    }
    
    sessions_data = requests.get(f"{api_url}/sessions/{session_type}", params=params).json()
    sessions = [dict_to_obj(s) for s in sessions_data]
    
    return render_template('sessions.html', session_type=session_type, data=sessions, start_date=start_date, end_date=end_date, user_id=user_id)


@measureme_bp.route('/intraday/<int:type_id>', methods=['GET'])
def view_intraday(type_id):
    api_url = get_api_url()
    user_id = request.args.get('user_id', default=1, type=int)
    
    bounds_resp = requests.get(f"{api_url}/bounds", params={'user_id': user_id}).json()
    start_date, end_date = parse_date_args(bounds_resp, request.args)
    
    tz_str = request.args.get('TZ')
    tz_obj = timezone.utc
    if tz_str:
        try:
            tz_obj = zoneinfo.ZoneInfo(tz_str)
        except Exception:
            pass
    
    # Needs UTC timestamps for the API
    start_utc = int(start_date.replace(tzinfo=tz_obj).timestamp())
    end_utc = int(end_date.replace(tzinfo=tz_obj).timestamp())

    params = {
        'user_id': user_id,
        'start_timestamp_utc': start_utc,
        'end_timestamp_utc': end_utc,
        'limit': 100,
        'order_desc': 'false'
    }
    
    intraday_data = requests.get(f"{api_url}/intraday/{type_id}", params=params).json()
    
            
    for d in intraday_data:
        dt = datetime.fromtimestamp(d['timestamp_utc'], tz=timezone.utc)
        local_time = dt.astimezone(tz_obj)
        d['timestamp_iso'] = local_time.isoformat()
        d['timestamp_yyyymmdd'] = local_time.strftime('%Y-%m-%d')
        d['timestamp_hhmm'] = local_time.strftime('%H:%M')
    
    # We also need the type metadata to render the title nicely
    types_resp = requests.get(f"{api_url}/types/intraday", params={'user_id': user_id}).json()
    type_info = next((t for t in types_resp if t['id'] == type_id), {"short_name": f"Metric {type_id}"})
    
    return render_template('intraday.html', type_info=type_info, data=intraday_data, start_date=start_date, end_date=end_date, user_id=user_id)


@measureme_bp.route('/metric/<metric_type>', methods=['GET'])
def view_metric(metric_type):
    api_url = get_api_url()
    user_id = request.args.get('user_id', default=1, type=int)
    
    bounds_resp = requests.get(f"{api_url}/bounds", params={'user_id': user_id}).json()
    start_date, end_date = parse_date_args(bounds_resp, request.args)
    
    params = {
        'user_id': user_id,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'limit': 100,
        'order_desc': 'false'
    }
    
    metrics_data = requests.get(f"{api_url}/metrics/{metric_type}", params=params).json()
    metrics = [dict_to_obj(m) for m in metrics_data][:100]
    
    return render_template('metrics.html', metric_type=metric_type, data=metrics, start_date=start_date, end_date=end_date, user_id=user_id)


@measureme_bp.route('/relaxation', methods=['GET'])
def view_relaxation():
    api_url = get_api_url()
    user_id = request.args.get('user_id', default=1, type=int)
    
    bounds_resp = requests.get(f"{api_url}/bounds", params={'user_id': user_id}).json()
    start_date, end_date = parse_date_args(bounds_resp, request.args)

    params = {
        'user_id': user_id,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'limit': 100,
        'order_desc': 'false'
    }
    
    results = requests.get(f"{api_url}/relaxation", params=params).json()
    
    return render_template("relaxation.html", data=results, start_date=start_date, end_date=end_date, user_id=user_id)


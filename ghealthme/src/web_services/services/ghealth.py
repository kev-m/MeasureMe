"""
Google Health API Webhook & Ingestion Blueprint.
Provides endpoints to trigger synchronization or accept webhooks from Google Health via Cloudflare tunnels.
"""
import logging
import os

from flask import Blueprint, request, jsonify
from ghealthme.db_queue import add_job

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

STORAGE_DIR = os.environ.get('STORAGE_DIR', 'storage')
GH_JOBS_DB = os.environ.get('GH_JOBS_DB', os.path.join(STORAGE_DIR,'gh_jobs.db'))

ghealth_bp = Blueprint('ghealth', __name__, url_prefix='/api/ghealth')

@ghealth_bp.route('/sync', methods=['POST'])
def trigger_sync():
    """
    Manually triggers a background sync of Google Health data.
    Clients or internal systems can hit this to enqueue a sync job.
    """
    add_job(endpoint="/api/ghealth/sync", payload={"trigger": "manual"}, jobs_path=GH_JOBS_DB)
    return jsonify({"status": "queued", "message": "Manual sync job enqueued successfully"}), 202

@ghealth_bp.route('/webhook', methods=['POST'])
def google_webhook():
    """
    Receives push notifications from Google Health API.
    Assuming Google supports Pub/Sub or similar webhook payloads.
    Data is enqueued quickly to keep the endpoint responsive.
    """
    payload = request.get_json() or {}
    
    # Store immediate payload into the local SQLite job queue
    add_job(endpoint="/api/ghealth/webhook", payload=payload, jobs_path=GH_JOBS_DB)
    
    # Return 204 to acknowledge receipt without blocking the webhook service
    return '', 204

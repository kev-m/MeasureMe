"""
OAuth 2.0 Blueprint for Google Health API.
Handles the OAuth consent flow and securely stores credentials.
"""
import os
import json
import logging
from flask import Blueprint, request, redirect, url_for, session, current_app
from google_auth_oauthlib.flow import Flow
from pathlib import Path
from ghealthme.ghealth_common import SCOPES

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

oauth_bp = Blueprint('oauth', __name__, url_prefix='/oauth')

load_dotenv()

STORAGE_DIR = os.environ.get('STORAGE_DIR', 'storage')
CREDENTIALS_FILE = os.path.join(STORAGE_DIR, os.environ.get('GHEALTH_CREDENTIALS', ''))
GH_TOKEN_FILE = os.path.join(STORAGE_DIR, "ghealth_tokens.json")
OAUTH_URI = os.environ.get('OAUTH_URI', 'http://localhost:8124/oauth/callback')

print(f"Found STORAGE_DIR: {STORAGE_DIR}")
print(f"Found CREDENTIALS_FILE: {CREDENTIALS_FILE}")
print(f"Found GH_TOKEN_FILE: {GH_TOKEN_FILE}")
print(f"Found OAUTH_URI: {OAUTH_URI}")

@oauth_bp.route('/login')
def login():
    """Initializes the OAuth 2.0 flow and redirects the user to Google."""
    if not Path(CREDENTIALS_FILE).exists():
        return f"Error: Ensure {CREDENTIALS_FILE} exists from Google Cloud Console.", 400

    # Ensure local dev allows insecure transport for oauthlib testing
    if request.host.startswith('localhost') or request.host.startswith('127.0.0.1'):
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    # Redirect URI is either explicitly configured or built dynamically
    redirect_uri = os.environ.get('OAUTH_URI')
    if not redirect_uri:
        redirect_uri = url_for('oauth.callback', _external=True)

    flow = Flow.from_client_secrets_file(
        str(CREDENTIALS_FILE),
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )

    # Note: Setting prompt='consent' forces a refresh token to be issued on every login
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    session.permanent = True
    session['state'] = state
    session['code_verifier'] = getattr(flow, 'code_verifier', None)
    
    # Save session explicitly to avoid race conditions with redirects
    session.modified = True
    return redirect(authorization_url)

@oauth_bp.route('/callback')
def callback():
    """Handles the callback from Google, extracts tokens, and saves them to disk."""
    if request.host.startswith('localhost') or request.host.startswith('127.0.0.1'):
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    state = session.get('state')
    
    if not state:
        logger.error(f"Session state missing. Host: {request.host}, Session: {list(session.keys())}")
        return "Missing session state. Ensure you are using the SAME host (localhost vs 127.0.0.1) for both login and callback. Ensure cookies are enabled.", 400

    if not Path(CREDENTIALS_FILE).exists():
        return f"Error: Ensure {CREDENTIALS_FILE} exists.", 400

    redirect_uri = os.environ.get('OAUTH_URI')
    if not redirect_uri:
        redirect_uri = url_for('oauth.callback', _external=True)

    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=redirect_uri
    )
    
    # Restore the PKCE code_verifier so that fetch_token passes verification
    if session.get('code_verifier'):
        flow.code_verifier = session['code_verifier']

    # Use the authorization server response to fetch tokens
    authorization_response = request.url
    # If trailing behind an HTTPS CF Tunnel but arriving locally as HTTP, force replace scheme
    if 'X-Forwarded-Proto' in request.headers and request.headers['X-Forwarded-Proto'] == 'https':
        authorization_response = authorization_response.replace('http://', 'https://')

    flow.fetch_token(authorization_response=authorization_response)
    
    credentials = flow.credentials
    Path(STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    with open(GH_TOKEN_FILE, 'w') as f:
        f.write(credentials.to_json())

    return "Google Health authentication successful! Tokens saved securely. You can close this window."

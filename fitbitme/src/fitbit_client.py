import os
import json
import base64
import requests
from urllib.parse import urlparse, parse_qs
import sys
from dotenv import load_dotenv

load_dotenv()

# Debugging
print(f"Found FB_CLIENT_ID: {os.environ.get('FB_CLIENT_ID')}")
print(f"Found FB_CLIENT_SECRET: {os.environ.get('FB_CLIENT_SECRET')}")

TOKEN_FILE = os.environ.get('TOKEN_FILE', 'storage/tokens.json')
FITBIT_API_BASE = 'https://api.fitbit.com/1/user/-'


class FitbitClient:
    def __init__(self, client_id=None, client_secret=None):
        self.client_id = client_id or os.environ.get('FB_CLIENT_ID')
        self.client_secret = client_secret or os.environ.get(
            'FB_CLIENT_SECRET')
        self.redirect_url = os.environ.get(
            'FB_REDIRECT_URL', 'http://localhost:8080/callback')
        self.auth_url_base = os.environ.get(
            'FB_AUTHORISE_URL', 'https://www.fitbit.com/oauth2/authorize')
        self.token_url = os.environ.get(
            'FB_TOKEN_URL', 'https://api.fitbit.com/oauth2/token')
        self.tokens = {}

        self._load_tokens()

    def _load_tokens(self):
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as f:
                self.tokens = json.load(f)

    def save_tokens(self, token_data):
        self.tokens = token_data
        with open(TOKEN_FILE, 'w') as f:
            json.dump(self.tokens, f, indent=4)

    def get_auth_header(self):
        auth_str = f"{self.client_id}:{self.client_secret}"
        b64_auth = base64.b64encode(auth_str.encode()).decode('utf-8')
        return {"Authorization": f"Basic {b64_auth}"}

    def refresh_token_if_needed(self):
        """Refreshes the OAuth token using the refresh_token."""
        # Note: Fitbit tokens expire in 8 hours. We could check timestamps,
        # but catching a 401 and auto-refreshing is safer.
        pass

    def fetch_data(self, endpoint, is_retry=False):
        """General purpose GET request for Fitbit API with auto-token refresh."""
        if not self.tokens.get('access_token'):
            raise Exception(
                "No access token available. Please run initial auth hook.")

        headers = {
            "Authorization": f"Bearer {self.tokens['access_token']}",
            "Accept": "application/json"
        }

        url = endpoint if endpoint.startswith(
            'http') else f"{FITBIT_API_BASE}/{endpoint}"
        response = requests.get(url, headers=headers)

        if response.status_code == 401 and not is_retry:
            print("Access token expired. Refreshing...")
            self.do_refresh_token()
            return self.fetch_data(endpoint, is_retry=True)

        response.raise_for_status()
        return response.json()

    def do_refresh_token(self):
        """Forces a token refresh."""
        url = self.token_url
        headers = self.get_auth_header()
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.tokens.get("refresh_token")
        }

        resp = requests.post(url, headers=headers, data=data)
        resp.raise_for_status()

        new_tokens = resp.json()
        self.save_tokens(new_tokens)
        print("Tokens refreshed and saved successfully.")

    def perform_initial_auth(self):
        """CLI flow for initial token generation."""
        if not self.client_id or not self.client_secret:
            print(
                "Error: FB_CLIENT_ID and FB_CLIENT_SECRET map must be set in .env file.")
            sys.exit(1)

        # Note: 'breathing_rate' or 'respiratory_rate' is historically tied to 'sleep' and 'oxygen_saturation' or just 'sleep' scope in Fitbit Web API.
        # Removing breathing_rate explicitly from the scope list to fix the invalid_scope error from Fitbit OAuth.
        # ADDING 'settings' scope because Fitbit requires it to create an "All Collections" webhook subscription.
        # ADDING 'respiratory_rate' for breathing rate and 'electrocardiogram'/'oxygen_saturation' for HRV/SPo2 if needed.
        scopes = "activity heartrate sleep weight nutrition profile settings respiratory_rate oxygen_saturation electrocardiogram"
        print("\n=== Fitbit Initial Authorization ===")
        print("1. Go to the following URL in your web browser:\n")

        # Using urllib.parse to safely encode the redirect URI if needed doesn't hurt, but we can just drop it into an f-string for simplicity
        import urllib.parse
        encoded_redirect = urllib.parse.quote(self.redirect_url, safe='')

        auth_url = f"{self.auth_url_base}?response_type=code&client_id={self.client_id}&redirect_uri={encoded_redirect}&scope={scopes}&expires_in=2592000"
        print(auth_url)
        print(f"\n2. Log in and 'Allow' access to MeasureMe.")
        print(
            f"3. You will be redirected to a {self.redirect_url} that will fail to load.")
        print("4. Copy the entire URL from the browser's address bar and paste it below:\n")

        redirected_url = input("Paste redirected URL here: ").strip()

        parsed = urlparse(redirected_url)
        qs = parse_qs(parsed.query)

        if 'code' not in qs:
            print("Error: Could not find 'code' parameter in the URL.")
            sys.exit(1)

        code = qs['code'][0]

        # Exchange code for token
        headers = self.get_auth_header()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = {
            "client_id": self.client_id,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_url,
            "code": code
        }

        print("Exchanging code for tokens...")
        resp = requests.post(self.token_url, headers=headers, data=data)
        if resp.status_code == 200:
            self.save_tokens(resp.json())
            print(
                "Success! Tokens saved to tokens.json. The worker can now act autonomously.")
        else:
            print(f"Error exchanging token: {resp.status_code}")
            print(resp.text)

    def create_subscription(self, subscription_id="1"):
        """Subscribes the application to receive webhook notifications for this user."""
        if not self.tokens.get('access_token'):
            raise Exception(
                "No access token available. Please run initial auth hook.")

        print(
            f"Creating Fitbit user subscription with ID {subscription_id}...")
        url = f"{FITBIT_API_BASE}/apiSubscriptions/{subscription_id}.json"

        headers = {
            "Authorization": f"Bearer {self.tokens['access_token']}",
            "Accept": "application/json"
        }

        response = requests.post(url, headers=headers)

        # Handle expired token gracefully like in fetch_data
        if response.status_code == 401:
            print("Access token expired. Refreshing...")
            self.do_refresh_token()
            headers["Authorization"] = f"Bearer {self.tokens['access_token']}"
            response = requests.post(url, headers=headers)

        if response.status_code in [200, 201]:
            print(f"Success! Subscription '{subscription_id}' created.")
            print(response.json())
        elif response.status_code == 409:
            print(
                f"Subscription '{subscription_id}' already exists for this user. You are ready to go!")
        else:
            print(
                f"Failed to create subscription. HTTP {response.status_code}")
            print(response.json())


if __name__ == "__main__":
    if len(sys.argv) > 1:
        client = FitbitClient()
        if sys.argv[1] == "auth":
            client.perform_initial_auth()
        elif sys.argv[1] == "subscribe":
            client.create_subscription()
        else:
            print("Unknown command. Use 'auth' or 'subscribe'.")
    else:
        print("Usage: python fitbit_client.py [auth|subscribe]")

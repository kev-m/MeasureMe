# This module is written to integrate with an existing Flask host:
# from flask import Flask
# from services.sms import sms_bp
# from services.fitbit import fitbit_bp

# app = Flask(__name__)

# # Register both services
# app.register_blueprint(sms_bp)
# app.register_blueprint(fitbit_bp)

# if __name__ == "__main__":
#     app.run(host='0.0.0.0', port=8123, debug=True, use_reloader=True)

# services/fitbit.py
import os
from flask import Blueprint, request
from dotenv import load_dotenv

# If you have queue_db.py, make sure you copy it to web_services too
from .queue_db import init_queue_db, add_job  

load_dotenv()

fitbit_bp = Blueprint('fitbit_service', __name__)

FITBIT_VERIFY_TOKEN = os.environ.get('FITBIT_VERIFY_TOKEN', '')
QUEUE_DB_PATH = os.environ.get('QUEUE_DB_PATH', 'storage/jobs.db')
CONFIG_SECRET = os.environ.get("CONFIG_SECRET", "supersecret123")
TZ_FILE_PATH = os.environ.get('TZ_FILE_PATH', 'storage/timezone.txt')


print(f"Found FITBIT_VERIFY_TOKEN: {FITBIT_VERIFY_TOKEN}")
print(f"Found QUEUE_DB_PATH: {QUEUE_DB_PATH}")
print(f"Found CONFIG_SECRET: {CONFIG_SECRET}")
print(f"Found TZ_FILE_PATH: {TZ_FILE_PATH}")

init_queue_db(db_path=QUEUE_DB_PATH)

@fitbit_bp.route('/magik/webhook', methods=['GET'])
def verify_webhook():
    verify_token = request.args.get('verify')
    if verify_token == FITBIT_VERIFY_TOKEN:
        print("Webhook verified successfully.")
        return '', 204
    else:
        print(f"Webhook verification failed: Invalid token {verify_token} != {FITBIT_VERIFY_TOKEN}.")
        return 'Not Found', 404

@fitbit_bp.route('/magik/webhook', methods=['POST'])
def receive_event():
    payload = request.get_json()
    if payload:
        print(f"Received {len(payload)} events. Queueing for background processing.")
        try:
            add_job(payload, db_path=QUEUE_DB_PATH)
        except Exception as e:
            print(f"Failed to queue job: {e}")
    return '', 204

@fitbit_bp.route("/magik/config/timezone/<secret>", methods=["GET", "POST"])
def config_timezone(secret):
    if secret != CONFIG_SECRET:
        return "Unauthorized", 403
        
    message = ""
    if request.method == "POST":
        new_tz = request.form.get("timezone", "").strip()
        if new_tz:
            # Ensure storage dir exists
            os.makedirs(os.path.dirname(TZ_FILE_PATH), exist_ok=True)
            with open(TZ_FILE_PATH, "w") as f:
                f.write(new_tz)
            message = f"<p style='color: green;'>Successfully updated timezone to: {new_tz}</p>"

    current_tz = "Europe/London (Default)"
    if os.path.exists(TZ_FILE_PATH):
        with open(TZ_FILE_PATH, "r") as f:
            current_tz = f.read().strip()
    else:
        current_tz = os.environ.get("USER_TIMEZONE", current_tz)

    return f'''
    <html>
        <head>
            <title>HealthyMe - Timezone Config</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: sans-serif; padding: 2rem; max-width: 400px; margin: auto; }}
                input, button {{ font-size: 1rem; padding: 0.5rem; width: 100%; box-sizing: border-box; margin-top: 0.5rem; }}
                button {{ background-color: #007bff; color: white; border: none; cursor: pointer; }}
            </style>
        </head>
        <body>
            <h2>Worker Timezone Config</h2>
            {message}
            <p><strong>Current Timezone:</strong><br/>{current_tz}</p>
            <form method="POST">
                <label>Set New Timezone (IANA format):</label>
                <input type="text" name="timezone" placeholder="e.g. Asia/Tokyo" required>
                <button type="submit">Update</button>
            </form>
            <p style="font-size: 0.8rem; color: #666; margin-top: 2rem;">Valid examples: Europe/London, Asia/Tokyo, America/New_York</p>
        </body>
    </html>
    '''
# main.py
import os
from flask import Flask
from services.oauth import oauth_bp
from services.ghealth import ghealth_bp

app = Flask(__name__)
# Secret key needed for session management in OAuth flow
# Using a fixed key ensures sessions survive development reloads
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default-dev-secret-key-change-in-prod')

# Register blueprints
app.register_blueprint(oauth_bp)
app.register_blueprint(ghealth_bp)

@app.route('/')
def health_check():
    return "MeasureMe GHealth Services Running"

if __name__ == "__main__":
    # Ensure port doesn't conflict with legacy fitbitme (8123) or measureme-web (5000)
    app.run(host='0.0.0.0', port=8124, debug=True, use_reloader=True)

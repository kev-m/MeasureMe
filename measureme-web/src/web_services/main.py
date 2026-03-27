# main.py
from flask import Flask
from services.measureme import measureme_bp
from services.measureme_api import measureme_api_bp

app = Flask(__name__)

# Register both services
app.register_blueprint(measureme_bp)
app.register_blueprint(measureme_api_bp)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8124, debug=True, use_reloader=True)
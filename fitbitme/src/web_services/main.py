# main.py
from flask import Flask
from services.fitbit import fitbit_bp

app = Flask(__name__)

# Register both services
app.register_blueprint(fitbit_bp)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8123, debug=True, use_reloader=True)
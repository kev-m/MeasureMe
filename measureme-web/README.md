# MeasureMe Web

The **MeasureMe Web** project is a lightweight Flask-based web dashboard and REST API acting as the presentation tier for the MeasureMe ecosystem. It reads and charts telemetry from the central MeasureMe SQLite/MariaDB database.

## Architecture

* **REST API (`measureme_api.py`):** Wraps the MeasureMe SQLAlchemy database connection, exposing JSON endpoints to fetch metrics, sessions, and multi-user configurations.
* **Web UI (`measureme.py`):** Acts entirely as a frontend client consuming the REST API, using Jinja templates to visualise data (e.g., daily sleep overlays, heart rate telemetry mapping).

## Configuration

To configure the application, you should create a `.env` file in the root of the `measureme-web` directory (or within `src/web_services/services/` if running locally). 

### Required Variables

**`.env`:**
```env
# Define the connection string (SQLAlchemy URI) or absolute path to the MeasureMe database.
MEASUREME_DB=sqlite:////absolute/path/to/your/measureme.db

# Optional deployment variables
RSYNC_HOST=your_nas_hostname
RSYNC_PATH=/share/homes/administrator/web_services
```

*(Note: In local development, the `MEASUREME_DB` path might be defined as an absolute file path pointing to the `FitBitMe/storage` directory, or wherever the ingestion worker is storing data.)*

## Running the Application

Ensure the virtual environment is active and all required packages from `requirements.txt` are installed.

```bash
cd D:\Dev\HealthyMe_top\MeasureMe\measureme-web
pip install -r requirements.txt
python .\src\web_services\main.py
```


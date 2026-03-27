# FitBitMe

**FitBitMe** is the live ingestion webhook receiver and asynchronous worker for the MeasureMe ecosystem. It ensures that intraday metrics, daily activities, and sleep summaries seamlessly stream from Fitbit APIs into your locally hosted `measureme` database, without exposing your database directly to the internet.

## Architecture

* **Receiver (`receiver.py`):** Acts as a high-speed HTTP endpoint that captures incoming webhook notifications from Fitbit. Because this interacts with the public internet (usually via a Cloudflare tunnel), it is kept intentionally thin. It instantly accepts payloads and writes them to a local SQLite job queue (`jobs.db`).
* **Worker (`worker.py`):** A persistent background process that monitors `jobs.db`. It pops jobs off the queue, reaches back out to the Fitbit API (using OAuth2) to pull the full payload, parses the data, and writes it directly into the `MeasureMe` database using the core `measureme` library.

## Configuration

To configure FitBitMe, you must provide `.env` files that contain sensitive OAuth secrets. 

You need an `.env` file either located at the root of `fitbitme/` or within its source directories (e.g. `src/web_services/services/.env`). The core environment variables required for full operation are:

**`.env`:**
```env
# 1. Fitbit OAuth Constraints
FB_CLIENT_ID=your_oauth_client_id
FB_CLIENT_SECRET=your_oauth_client_secret
FB_REDIRECT_URL=http://localhost:8080/callback
FB_AUTHORISE_URL=https://www.fitbit.com/oauth2/authorize
FB_TOKEN_URL=https://api.fitbit.com/oauth2/token

# 2. Local Storage and Queue Configuration
# It is vital to use absolute paths or securely mounted volume paths here.
QUEUE_DB_PATH=/absolute/path/to/FitBitMe/storage/jobs.db
TOKEN_FILE=/absolute/path/to/FitBitMe/storage/tokens.json

# 3. Database Targeting
# Points to the central MeasureMe database that the worker will push to.
MEASUREME_DB=/absolute/path/to/MeasureMe/measureme.db
```

*(For comprehensive instructions on generating `FB_CLIENT_ID` and pairing your account, refer to [`FITBIT_SETUP.md`](./FITBIT_SETUP.md).)*

## Running FitBitMe

Start the required services sequentially. Both the receiver and the worker need to be online for continuous categorisation.

```bash
pip install -r requirements.txt

# Start the OAuth Token Flow / Webhook Receiver
python src/web_services/main.py

# In a separate terminal, start the Background Polling Worker
python src/worker.py
```

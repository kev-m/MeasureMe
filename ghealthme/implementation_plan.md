# Implementation Plan: Google Health API Integration (`ghealthme`)

## Phase 1: Core Connector & Database Setup
1. **Scaffold `ghealthme` Project Structure:**
   - Define project configuration (e.g., `pyproject.toml`) for `ghealthme`, specifying dependencies including `Flask`, `google-auth-oauthlib`, `requests`, and the local `measureme` core.
   - Replicate the independent SQLite job queue mechanism (`jobs.db`) from `fitbitme` to smoothly handle asynchronous bulk API polling/ingestion.
   - *Note:* `ghealthme` runs entirely independent of `fitbitme` since the latter is being deprecated, and will maintain its own isolated queue.
2. **Library Implementation (`ghealthme.core`):**
   - Build a `GoogleHealthClient` / `GHealthFetcher` class to manage authenticated requests, using the native `requests` library and `AuthorizedSession` from `google-auth` for seamless REST API consumption.
   - Map payloads based on the [Google Health API Migration](https://developers.google.com/health/migration) directly to the `measureme` pure SQLAlchemy core models (`SleepSession`, `ExerciseSession`, `HealthIntraday`, `HealthMetric`).
   - Ensure the `global_id` mapping heavily relies on Google’s immutable entity IDs to ensure perfect data deduplication.

## Phase 2: OAuth 2.0 & Webhook/Polling Blueprints
1. **OAuth Blueprint (`ghealthme\src\web_services\services\oauth.py`):**
   - Must use Google's official libraries (`google-auth-oauthlib`) to comply with Google Health API requirements.
   - **`/login` Endpoint:** Redirects the user to Google’s OAuth 2.0 consent screen, specifically requesting `access_type=offline` and `prompt=consent` to secure long-lived Refresh Tokens.
   - **`/callback` Endpoint:** Handles the authorization code exchange out of the callback, extracts credentials, and stores them in the local `ghealthme\storage` directory as per-user JSON, suitable for re-use by the blueprint and the stand-alone ingestor.
2. **Common Library (ghealthme\src\ghealth_common.py):**
   - Contains the common code shared between the blueprint data ingestor  and the stand-alone ingestor.
3. **Stand-alone Ingestor (ghealthme\scripts\ingest_ghealth.py):**
   - Contains the command-line ingestor, that uses the authenticated tokens to write recent data to the database (long term legacy data is added by `measureme\scripts\ingest_fitout.py`, but recent top-ups require a stand-alone Google Health API ingestor).
4. **Data Ingestion Blueprint (`ghealthme\src\web_services\services\ghealth.py`):**
   - Incorporate Cloudflare Tunnels (`cloudflared`) to expose the local Flask webhook endpoints securely without NAS port-forwarding.
   - If Google provides Webhook functionality analogous to Fitbit notifications, expose the receiver endpoints over the Tunnel to enqueue incoming payloads into `jobs.db`.
   - Implement manual trigger endpoints (e.g., `/api/ghealth/sync`) to queue backfills and manual sync jobs.
5. **Background Worker (`ghealthme\src\worker.py`):**
   - Create a background process to read from `jobs.db`, hit the Google API for bulk loads, translate responses, and commit them via SQLAlchemy directly to the core DB.

## Phase 3: Documentation
1. **Draft `GoogleHealth_setup.md`:**
   - **Step 1: Google Cloud Console:** Provide walkthrough for creating a new GCP project.
   - **Step 2: API Enablement:** Specify the exact Google Health APIs that must be explicitly enabled.
   - **Step 3: OAuth Consent Screen:** Detail setting up "External" vs "Internal" app types, specifying the exact required health permission scopes.
   - **Step 4: Credentials:** Provide instructions for generating Web Application OAuth Client IDs, explicitly covering whitelisting local callback URIs routed via CloudFlare Tunnels (e.g., `https://health.yourdomain.com/callback`), and retrieving the `CLIENT_ID` and `CLIENT_SECRET`.

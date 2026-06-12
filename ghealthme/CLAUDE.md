# Claude Sub-Project Rules: Google Health Ingestion Engine

## Environment & Lifecycle
- **Persistent Service:** `worker.py` is a long-running background service worker that processes the local SQLite queue (`jobs.db`). Do not run this interactively unless explicitly testing the daemon loop.
- **Local State:** Manages `jobs.db`. Do not clear or drop this queue database without explicit instructions.

## Operational Utility Scripts
When diagnosing API connectivity, verifying data schemas, or testing authentication, use the dedicated script wrappers inside the `.\scripts\` folder. The actual scripts are in `src\ghealthme\cli`.

Always execute them using the workspace virtual environment from this directory:

* **Update API Discovery Documents:** This changes rarely. Always ask permission first.
  `..\..\.venv\Scripts\python.exe scripts\update_discovery.py`
* **Check API Status & Auth:** 
  `..\..\.venv\Scripts\python.exe scripts\api_check.py`
* **Browse Raw Google Health Data:** 
  `..\..\.venv\Scripts\python.exe scripts\browse_ghealth.py`
* **Trigger Manual Data Ingestion:** 
  `..\..\.venv\Scripts\python.exe scripts\ingest_ghealth.py`

## Common Command Cheatsheet
- **Run Service Worker:** `..\..\.venv\Scripts\python.exe worker.py`

# MeasureMe Ingestion Scripts

This directory contains utility scripts for importing historical and external data into the local MeasureMe database.

## `ingest_fitout.py`

The primary tool for importing historical data exported via Google Takeout (from Fitbit). It supports parsing zipped exports, resolving local timezones during travel, and converting weight metrics.

### Basic Usage

To import data from a specific date range into a local SQLite database:

```bash
python ingest_fitout.py "path/to/takeout-2026xxxx.zip" \
  --start 2024-01-01 \
  --end 2026-03-20 \
  --db "sqlite:///measureme.db"
```

### Full Command-Line Options

* `path`: **(Required)** Path to the Google Takeout export (supports `.zip` files directly or unzipped directories).
* `--start`: **(Required)** Start date in `YYYY-MM-DD` format.
* `--end`: **(Required)** End date in `YYYY-MM-DD` format.
* `--db`: SQLAlchemy Database URL. Defaults to `sqlite:///measureme_dev.db`.
* `--types`: Specify which health types to import (e.g., `sleep exercises resting_heart_rate`). Defaults to all.
* `--user-id`: The User ID to associate with the imported data. Defaults to `1`.
* `--timezone`: The default IANA timezone to use (e.g., `Europe/London`).
* `--holidays-csv`: Path to a CSV file to calculate local timezones while travelling (see below).
* `--weight-to-kgs`: A flag to convert TakeOut weight data from pounds (lbs) to kilograms (kg).

---

### Timezones and the Holidays CSV

When importing historical intraday data (which Google provides strictly in UTC), generating correct boundaries requires knowledge of the local timezone you were in at the time.

By passing a `--holidays-csv`, the script will dynamically offset the timestamp bounds so that your sleep and telemetry naturally map to the destination you were visiting. 

If the script detects a date within a holiday range, it will try to map the `Destination` column to a standard IANA timezone. It checks for:
1. Valid explicit IANA strings (e.g., `Asia/Tokyo`).
2. Mapped country locations defined internally (e.g., `Spain (Mallorca)` maps to `Europe/Madrid`).

#### Example `holidays.csv` Schema

The CSV requires the following exact headers. Dates must be formatted as `YYYY/MM/DD`.

```csv
Departure Date,Return Date,Destination
2024/10/10,2024/10/18,Italy
2025/12/20,2026/01/05,Asia/Tokyo
2026/05/01,2026/05/10,Spain (Mallorca)
```

**Execution Example with Holidays:**

```bash
python ingest_fitout.py "path/to/takeout.zip" \
  --start 2024-10-01 \
  --end 2024-11-01 \
  --timezone "Europe/London" \
  --holidays-csv "holidays.csv" \
  --weight-to-kgs
```

In this example, data before `2024/10/10` and after `2024/10/18` will default to `Europe/London`, while data bounded within the trip will automatically shift to `Europe/Rome` (mapped from `Italy`).
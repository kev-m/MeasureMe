# MeasureMe (Core Library)
[![GitHub license](https://img.shields.io/github/license/kev-m/MeasureMe)](https://github.com/kev-m/MeasureMe/blob/development/LICENSE.txt)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/measureme?logo=pypi)](https://pypi.org/project/measureme/)
[![semver](https://img.shields.io/badge/semver-2.0.0-blue)](https://semver.org/)
[![GitHub tag (latest SemVer)](https://img.shields.io/github/v/tag/kev-m/MeasureMe?sort=semver)](https://github.com/kev-m/MeasureMe/releases)
[![Code style: autopep8](https://img.shields.io/badge/code%20style-autopep8-000000.svg)](https://pypi.org/project/autopep8/)

<!-- ![MeasureMe logo](https://github.com/kev-m/MeasureMe/blob/development/docs/source/figures/Logo_small.png) -->

The **MeasureMe** project is an open source Python library for storing health data in a vendor agnostic way.
It utilizes SQLAlchemy to provide a privacy-first, local database (SQLite/MariaDB) to store your metrics safely without requiring cloud servers.

Integrations are required to fetch data from proprietary sources and write them to the database.

## Installation

Requires Python 3.9+.

Use pip to install:
```bash
pip install measureme
```

For local development, clone the repository and install the development requirements:
```bash
pip install -r requirements-dev.txt
```

## Example

How to use MeasureMe:

### FitBit Ingestion

An example script has been provided that ingests [FitBit data](https://www.fitbit.com/settings/data/export),
exported using [Google Takeout](https://takeout.google.com/settings/takeout/custom/fitbit?pli=1).

The script relies on [FitOut](https://github.com/kev-m/FitOut), which is installed via pypi:
```bash
pip install fitout
```

#### Export FitBit Data using Google TakeOut
Export your [FitBit data](https://www.fitbit.com/settings/data/export), using [Google Takeout](https://takeout.google.com/settings/takeout/custom/fitbit?pli=1).

Once the export is complete, download the zip file. I use `C:/Dev/Fitbit/Google/`. 
This directory is the `takeout_dir`.

#### Ingest the Data

The `ingest_fitout` is available as a callable script, and can be used directly:
```bash
ingest_fitout "C:/Dev/Fitbit/Google/takeout-20260320T162823Z-3-001.zip" --start 2024-01-01 --end 2026-03-20
```
By default, this will create and populate a local SQLite database named `measureme_dev.db` in the current directory.
Once the data has been ingested, it can be queried using the MeasureMe library.

See the [tool README](https://github.com/kev-m/MeasureMe/blob/development/measureme/README_CLI.md) for full details.

### Trivial Example

*For the full, runnable script, see [`examples/basic_query.py`](https://github.com/kev-m/MeasureMe/blob/development/measureme/examples/basic_query.py).*

```python
from measureme.database import get_engine, get_session_maker
from measureme.models import HealthMetric, HealthSession

engine = get_engine("sqlite:///measureme_dev.db")
Session = get_session_maker(engine)

with Session() as session:
    # Query the 5 most recent sleep sessions
    recent_sleep = session.query(HealthSession)\
        .filter(HealthSession.session_type == 'sleep')\
        .order_by(HealthSession.start_time.desc())\
        .limit(5).all()
        
    for sleep in recent_sleep:
        duration_hrs = sleep.duration_seconds / 3600.0 if sleep.duration_seconds else 0
        print(f"Date: {sleep.start_time.date()}, Duration: {duration_hrs:.2f} hours")
```

### Plotting Example with Numpy and Matplotlib
**Note:** To run this example, you will need to install the dependencies:
```bash
pip install matplotlib numpy PyQt6
```

*For the full, runnable script, see [`examples/plot_calmness.py`](https://github.com/kev-m/MeasureMe/blob/development/measureme/examples/plot_calmness.py).*

```python
import numpy as np
import fitout as fo
from measureme.database import get_engine, get_session_maker
from measureme.models import HealthMetric

# 1. Fetch raw data from MeasureMe
# ... (Querying logic omitted for brevity) ...

# 2. Extract database rows into lists aligned to continuous dates
breathing_raw = extract_aligned_data(metrics, dates, 'breathing_rate')
hrv_raw = extract_aligned_data(metrics, dates, 'hrv_rmssd')
rhr_raw = extract_aligned_data(metrics, dates, 'resting_heart_rate')

# 3. Apply cleaning algorithms (Clean-On-Read feature via FitOut helpers)
breathing_data = fo.fill_missing_with_neighbours(breathing_raw)
hrv_data = fo.fill_missing_with_neighbours(hrv_raw)

breathing_data = fo.fix_invalid_data_points(breathing_data, 10, 20)
hrv_data = fo.fix_invalid_data_points(hrv_data, 20, 50)

# 4. Create the Derived Calmness Metric and plot!
breathing_arr = np.array(breathing_data).astype(float)
hrv_arr = np.array(hrv_data).astype(float)
rhr_arr = np.array(rhr_data).astype(float)

# Equation: 100 - (RHR/2 + breathing rate*2 - HRV)
calmness_index = 100 - (rhr_arr / 2. + breathing_arr * 2. - hrv_arr)
```

### More Examples
For more examples, see the [examples](https://github.com/kev-m/MeasureMe/tree/development/measureme/examples) directory.

## Contributing
If you'd like to contribute to **MeasureMe**, follow the guidelines outlined in the [Contributing Guide](https://github.com/kev-m/MeasureMe/blob/development/CONTRIBUTING.md).

## License
See [`LICENSE.txt`](https://github.com/kev-m/MeasureMe/blob/development/LICENSE.txt) for more information.

## Contact
For inquiries and discussion, use [MeasureMe Discussions](https://github.com/kev-m/MeasureMe/discussions).

## Issues
For issues related to this Python implementation, visit the [Issues](https://github.com/kev-m/MeasureMe/issues) page.

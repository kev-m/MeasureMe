# MeasureMe Ecosystem
The **MeasureMe** project is an open-source, Python-based health data ecosystem. It provides a cohesive suite of tools designed to store, ingest, and visualise personal health metrics in a privacy-first, vendor-agnostic way using local databases.

This repository is a monorepo that contains the live operational components of the ecosystem:

1. **[MeasureMe Core Library (`/measureme`)](./measureme/README.md):** 
   The central database models, SQLAlchemy schemas, and querying interfaces. This library provides the absolute source of truth for the health schema and is published to PyPI as the `measureme` package.
2. **[MeasureMe Web (`/measureme-web`)](./measureme-web/README.md):** 
   A lightweight Flask-based web dashboard and REST API. It acts as the primary presentation tier to read and chart telemetry from the MeasureMe database.
3. **[FitBitMe (`/fitbitme`)](./fitbitme/README.md):** 
   The live ingestion tier. A webhook receiver and asynchronous worker that securely streams continuous, near-real-time data from Fitbit directly into your local MeasureMe database.

A fourth tool, [`FitOut`](https://github.com/kev-m/FitOut/), used to access Google TakeOut data, is maintained separately.

## Environment Setup

Throughout this repository, certain components rely on environment variables (`.env` files) to manage secrets, file paths, and deployment configurations.

For configuration relating specifically to the Web Dashboard or the Fitbit Webhooks, please refer to the respective project READMEs:
* Setup MeasureMe Web [Here](./measureme-web/README.md#configuration)
* Setup FitBitMe [Here](./fitbitme/README.md#configuration)

## Contributing
Please review our [`CONTRIBUTING.md`](./CONTRIBUTING.md) to adhere to code styles, PEP 8 formatting, and the monorepo deployment workflows.



## Issues
For issues related to this Python implementation, visit the [Issues](https://github.com/kev-m/MeasureMe/issues) page.

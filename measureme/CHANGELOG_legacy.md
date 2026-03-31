# Changelog

## v1.1.0 (2026-03-27)

#### New Features

* Add missing parameters to intraday queries.
* Expose Intraday types as human-readable strings.
#### Fixes

* Adding limit parameter to get_daily_metrics.

Full set of changes: [`v1.0.0...v1.1.0`](https://github.com/kev-m/MeasureMe/compare/core-v1.0.0...core-v1.1.0)

## v1.0.0 (2026-03-25)

#### New Features

* Using start time (UTC) as global ID.
* (database): Adding foreign key enforcement.
* (models): Splitting HealthSession into explicit Sleep and Exercise.
* Adding MeasureMeQuery abstraction layer with examples.
#### Fixes

* Capture breathing rate to 1 decimal point.
* Skip naps in relaxation data query.
* Updating query interface to support updated schema.
* Fixing ingestor to work with updated schema.
* Optimising with caches and batch updates to speed up large window inserts.

Full set of changes: [`v0.4.0...v1.0.0`](https://github.com/kev-m/MeasureMe/compare/core-v0.4.0...core-v1.0.0)

## v0.4.0 (2026-03-23)

#### New Features

* Exposing ingest_fitout as an installed script.

Full set of changes: [`v0.3.0...v0.4.0`](https://github.com/kev-m/MeasureMe/compare/core-v0.3.0...core-v0.4.0)

## v0.3.0 (2026-03-23)

#### New Features

* (models): Adding timezone support.

Full set of changes: [`v0.2.0...v0.3.0`](https://github.com/kev-m/MeasureMe/compare/core-v0.2.0...core-v0.3.0)

## v0.2.0 (2026-03-21)

#### New Features

* (test): Adding tests.

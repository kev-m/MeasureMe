# Changelog

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

Full set of changes: [`v0.4.0...v1.0.0`](https://github.com/kev-m/MeasureMe/compare/v0.4.0...v1.0.0)

## v0.4.0 (2026-03-23)

#### New Features

* Exposing ingest_fitout as an installed script.
#### Fixes

* Minor fixes to improve holiday calendar usage.
#### Docs

* Adding README to explain how to use the ingest_fitout tool.
#### Others

* Adding holiday tests.

Full set of changes: [`v0.3.0...v0.4.0`](https://github.com/kev-m/MeasureMe/compare/v0.3.0...v0.4.0)

## v0.3.0 (2026-03-23)

#### New Features

* (tools): Adding travel/holiday calendar support to the ingestor, to ensure that times are always local naive.
* (models): Adding timezone support.
* (tests): Adding tests
#### Fixes

* Bugfixes to correct for weight units and conversions.
* Bugfixes to correct for correct timezone usage.

Full set of changes: [`v0.2.0...v0.3.0`](https://github.com/kev-m/MeasureMe/compare/v0.2.0...v0.3.0)

## v0.2.0 (2026-03-21)

#### New Features

* (test): Adding tests.

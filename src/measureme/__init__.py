"""A vendor-abstract health data library."""

# Semantic Versioning according to https://semver.org/spec/v2.0.0.html
__version__ = "1.0.0" # Split HealthSession into explicit Sleep and Exercise. Using start time (UTC) as global ID.

from .query import MeasureMeQuery

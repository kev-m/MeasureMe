"""A vendor-abstract health data library."""
# Tag with prefix: git tag core-v

# Semantic Versioning according to https://semver.org/spec/v2.0.0.html
__version__ = "1.2.1" # Fix: Compute %deep sleep to match FitBit app: deep/(sleep + awake)

from .query import MeasureMeQuery

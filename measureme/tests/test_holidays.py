import sys
import os
from datetime import date
import pytest

from measureme.cli.ingest_fitout import get_timezone_for_date

def test_get_timezone_no_date():
    assert get_timezone_for_date(None, []) == "Europe/London"
    assert get_timezone_for_date(None, [], default_tz="America/New_York") == "America/New_York"

def test_get_timezone_no_holidays():
    d = date(2026, 3, 17)
    assert get_timezone_for_date(d, []) == "Europe/London"

def test_get_timezone_during_holiday():
    holidays = [
        {'start': date(2026, 3, 10), 'end': date(2026, 3, 20), 'destination': 'Italy'}
    ]
    
    # Before holiday
    assert get_timezone_for_date(date(2026, 3, 9), holidays) == "Europe/London"
    # During holiday
    assert get_timezone_for_date(date(2026, 3, 15), holidays) == "Europe/Rome"
    # End of holiday
    assert get_timezone_for_date(date(2026, 3, 20), holidays) == "Europe/Rome"
    # After holiday
    assert get_timezone_for_date(date(2026, 3, 21), holidays) == "Europe/London"

def test_get_timezone_with_parentheses():
    holidays = [
        {'start': date(2026, 5, 1), 'end': date(2026, 5, 10), 'destination': 'Spain (Mallorca)'}
    ]
    assert get_timezone_for_date(date(2026, 5, 5), holidays) == "Europe/Madrid"

def test_get_timezone_explicit_iana():
    holidays = [
        {'start': date(2026, 6, 1), 'end': date(2026, 6, 15), 'destination': 'Asia/Tokyo'}
    ]
    # 'Asia/Tokyo' is not in DESTINATION_TZ_MAP, but is a valid IANA string
    assert get_timezone_for_date(date(2026, 6, 10), holidays) == "Asia/Tokyo"

def test_get_timezone_unknown_destination_fallback():
    holidays = [
        {'start': date(2026, 4, 1), 'end': date(2026, 4, 10), 'destination': 'Mars'}
    ]
    # 'Mars' is not in DESTINATION_TZ_MAP, so it should fallback to default
    assert get_timezone_for_date(date(2026, 4, 5), holidays) == "Europe/London"

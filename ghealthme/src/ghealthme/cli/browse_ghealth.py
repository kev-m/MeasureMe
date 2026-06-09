"""
Standalone CLI script to browse Google Health API data and print to screen as CSV.
"""
import os
import sys
import argparse
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any, List
from ghealthme.ghealth_common import load_credentials, GHealthFetcher, extract_start_end_times, BASIC_TYPES, ALL_TYPES

# Setup logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("browse_ghealth")

class GHealthCSVMapper:
    """Prints Google Health API responses as CSV to stdout."""
    def __init__(self, tz_name: str = "Europe/London"):
        self.tz_name = tz_name
        try:
            self.tz_info = ZoneInfo(tz_name)
        except:
            self.tz_info = None

    def print_section(self, title, headers, rows):
        print(f"\n# {title}")
        print(",".join(headers))
        for row in rows:
            print(",".join(map(str, row)))

    def process_data_points_by_type(self, collection_type: str, points: List[Dict[str, Any]]):
        if not points:
            return

        if collection_type == 'intraday_heart_rate':
            headers = ["timestamp", "bpm"]
            rows = []
            for p in points:
                data = p.get('heartRate', {})
                time_obj = data.get('sampleTime', {})
                time_str = time_obj.get('physicalTime') if isinstance(time_obj, dict) else str(time_obj)
                bpm = data.get('beatsPerMinute')
                if time_str and bpm:
                    rows.append([time_str, bpm])
            self.print_section("Heart Rate (Intraday)", headers, rows)

        elif collection_type == 'sleep':
            headers = ["start", "end", "minutes_asleep", "deep_m", "light_m", "rem_m", "awake_m"]
            rows = []
            for p in points:
                entry = p.get('sleep', {})
                interval = entry.get('interval', {})
                try:
                    _, start_time, end_time = extract_start_end_times(self.tz_info, interval)
                except:
                    continue
                
                summary = entry.get('summary', {})
                stages = summary.get('stagesSummary', [])
                
                def get_stage(key):
                    for s in stages:
                        if s.get('type') == key:
                            return s.get('minutes', 0)
                    return 0

                rows.append([
                    start_time.isoformat(),
                    end_time.isoformat(),
                    summary.get('minutesAsleep', 0),
                    get_stage('DEEP'),
                    get_stage('LIGHT'),
                    get_stage('REM'),
                    get_stage('AWAKE')
                ])
            self.print_section("Sleep Sessions", headers, rows)

        elif collection_type == 'resting_heart_rate':
            headers = ["date", "bpm"]
            rows = []
            for p in points:
                data = p.get('dailyRestingHeartRate', {})
                d = data.get('date', {})
                date_str = f"{d.get('year')}-{d.get('month'):02d}-{d.get('day'):02d}" if d else ""
                bpm = data.get('beatsPerMinute')
                if date_str and bpm:
                    rows.append([date_str, bpm])
            self.print_section("Daily Resting Heart Rate", headers, rows)

        elif collection_type == 'hrv':
            headers = ["date", "hrv_rmssd_ms"]
            rows = []
            for p in points:
                data = p.get('dailyHeartRateVariability', {})
                d = data.get('date', {})
                date_str = f"{d.get('year')}-{d.get('month'):02d}-{d.get('day'):02d}" if d else ""
                val = data.get('averageHeartRateVariabilityMilliseconds')
                if date_str and val:
                    rows.append([date_str, val])
            self.print_section("Daily Heart Rate Variability", headers, rows)

        elif collection_type == 'exercise':
            headers = ["start", "end", "activity", "kcal", "steps", "distance_m", "avg_hr"]
            rows = []
            for p in points:
                entry = p.get('exercise', {})
                interval = entry.get('interval', {})
                try:
                    _, start_time, end_time = extract_start_end_times(self.tz_info, interval)
                except:
                    continue
                
                metrics = entry.get('summary', {}).get('metricsSummary', {})
                rows.append([
                    start_time.isoformat(),
                    end_time.isoformat(),
                    entry.get('displayName', entry.get('exerciseType', 'UNKNOWN')),
                    metrics.get('caloriesKcal', 0),
                    metrics.get('steps', 0),
                    metrics.get('distanceMillimeters', 0),
                    metrics.get('averageHeartRateBeatsPerMinute', 0)
                ])
            self.print_section("Exercise Sessions", headers, rows)

        elif collection_type == 'weight':
            headers = ["timestamp", "weight_kg"]
            rows = []
            for p in points:
                data = p.get('weight', {})
                time_obj = data.get('sampleTime', {})
                time_str = time_obj.get('physicalTime') if isinstance(time_obj, dict) else str(time_obj)
                grams = data.get('weightGrams')
                if time_str and grams:
                    rows.append([time_str, grams / 1000.0])
            self.print_section("Weight Measurements", headers, rows)

        elif collection_type == 'breathing_rate':
            headers = ["timestamp", "breaths_per_min"]
            rows = []
            for p in points:
                data = p.get('respiratoryRateSleepSummary', {})
                time_obj = data.get('sampleTime', {})
                time_str = time_obj.get('physicalTime') if isinstance(time_obj, dict) else str(time_obj)
                stats = data.get('fullSleepStats', {})
                bpm = stats.get('breathsPerMinute')
                if time_str and bpm:
                    rows.append([time_str, bpm])
            self.print_section("Respiratory Rate (Sleep)", headers, rows)

def main():
    parser = argparse.ArgumentParser(description="Browse Google Health API data as CSV.")
    parser.add_argument('--start', type=str, required=True, help='Start date YYYY-MM-DD')
    parser.add_argument('--end', type=str, required=True, help='End date YYYY-MM-DD')
    parser.add_argument('--types', nargs='+', help=f'Collections to browse {ALL_TYPES}')
    parser.add_argument('--timezone', type=str, default="Europe/London", help='IANA timezone for local times.')

    args = parser.parse_args()
    
    token_file = os.environ.get('GH_TOKEN_FILE', "storage/ghealth_tokens.json")
    creds = load_credentials(token_file)
    if not creds or not creds.valid:
        print("Error: No valid credentials found.")
        sys.exit(1)

    s_date = datetime.strptime(args.start, '%Y-%m-%d')
    e_date = datetime.strptime(args.end, '%Y-%m-%d')

    mapper = GHealthCSVMapper(tz_name=args.timezone)
    fetcher = GHealthFetcher(credentials=creds, mapper=mapper)

    all_types = BASIC_TYPES
    types_to_run = args.types if args.types else all_types

    for t in types_to_run:
        try:
            fetcher.fetch_and_process(t, s_date, e_date)
        except Exception as e:
            print(f"Error fetching {t}: {e}")

if __name__ == "__main__":
    main()

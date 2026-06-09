"""
Standalone CLI script to browse Google Health API data and print to screen as CSV.
"""
import os
import sys
import argparse
import logging
import json
from datetime import datetime, date, timedelta
from ghealthme.ghealth_common import load_credentials, GHealthFetcher, extract_start_end_times

# Setup logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("browse_ghealth")

class GHealthCSVPrinter:
    """Helper to process Google Health API data points and print them as CSV."""
    def __init__(self, tz_name: str = "Europe/London"):
        self.tz_name = tz_name
        try:
            from zoneinfo import ZoneInfo
            self.tz_info = ZoneInfo(tz_name)
        except:
            self.tz_info = None

    def print_section(self, title, headers, rows):
        print(f"\n# {title}")
        print(",".join(headers))
        for row in rows:
            print(",".join(map(str, row)))

    def process_and_print(self, collection_type, points):
        if not points:
            return

        if collection_type == 'intraday_heart_rate':
            self.print_heart_rate(points)
        elif collection_type == 'sleep':
            self.print_sleep(points)
        elif collection_type == 'resting_heart_rate':
            self.print_resting_heart_rate(points)
        elif collection_type == 'hrv':
            self.print_hrv(points)
        elif collection_type == 'exercise':
            self.print_exercise(points)
        elif collection_type == 'weight':
            self.print_weight(points)
        elif collection_type == 'breathing_rate':
            self.print_breathing_rate(points)

    def print_heart_rate(self, points):
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

    def print_resting_heart_rate(self, points):
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

    def print_hrv(self, points):
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

    def print_sleep(self, points):
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

    def print_exercise(self, points):
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

    def print_weight(self, points):
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

    def print_breathing_rate(self, points):
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
    parser.add_argument('--types', nargs='+', help='Collections to browse (sleep, exercise, weight, hrv, resting_heart_rate, breathing_rate, intraday_heart_rate)')
    parser.add_argument('--timezone', type=str, default="Europe/London", help='IANA timezone for local times.')

    args = parser.parse_args()
    
    token_file = os.environ.get('GH_TOKEN_FILE', "storage/ghealth_tokens.json")
    creds = load_credentials(token_file)
    if not creds or not creds.valid:
        print("Error: No valid credentials found.")
        sys.exit(1)

    s_date = datetime.strptime(args.start, '%Y-%m-%d')
    e_date = datetime.strptime(args.end, '%Y-%m-%d')

    printer = GHealthCSVPrinter(tz_name=args.timezone)
    fetcher = GHealthFetcher(credentials=creds, mapper=None) # We don't need the DB mapper

    all_types = ['sleep', 'exercise', 'weight', 'hrv', 'resting_heart_rate', 'breathing_rate', 'intraday_heart_rate']
    types_to_run = args.types if args.types else all_types

    for t in types_to_run:
        # We'll hijack the fetcher's internal logic to get points instead of processing them
        # fetch_and_process normally calls mapper.process_data_points
        # Since we passed mapper=None, we can't use it directly without a small tweak or just writing the logic here.
        
        # Build filter expressions (copied from fetcher logic)
        start_str_rfc = s_date.strftime('%Y-%m-%dT00:00:00.000Z')
        end_str_rfc = e_date.strftime('%Y-%m-%dT23:59:59.999Z')
        start_str_civil = s_date.strftime('%Y-%m-%dT00:00:00')
        end_str_civil = e_date.strftime('%Y-%m-%dT23:59:59')
        date_start = s_date.strftime('%Y-%m-%d')
        date_end_plus_1 = (e_date + timedelta(days=1)).strftime('%Y-%m-%d')

        parent = None
        filter_expr = None
        
        if t == 'sleep':
            parent = 'users/me/dataTypes/sleep'
            filter_expr = f'sleep.interval.end_time >= "{start_str_rfc}" AND sleep.interval.end_time < "{end_str_rfc}"'
        elif t == 'exercise':
            parent = 'users/me/dataTypes/exercise'
            filter_expr = f'exercise.interval.civil_start_time >= "{start_str_civil}" AND exercise.interval.civil_start_time < "{end_str_civil}"'
        elif t == 'hrv':
            parent = 'users/me/dataTypes/daily-heart-rate-variability'
            filter_expr = f'daily_heart_rate_variability.date >= "{date_start}" AND daily_heart_rate_variability.date < "{date_end_plus_1}"'
        elif t == 'weight':
            parent = 'users/me/dataTypes/weight'
            filter_expr = f'weight.sample_time.physical_time >= "{start_str_rfc}" AND weight.sample_time.physical_time < "{end_str_rfc}"'
        elif t == 'resting_heart_rate':
            parent = 'users/me/dataTypes/daily-resting-heart-rate'
            filter_expr = f'daily_resting_heart_rate.date >= "{date_start}" AND daily_resting_heart_rate.date < "{date_end_plus_1}"'
        elif t == 'breathing_rate':
            parent = 'users/me/dataTypes/respiratory-rate-sleep-summary'
            filter_expr = f'respiratory_rate_sleep_summary.sample_time.physical_time >= "{start_str_rfc}" AND respiratory_rate_sleep_summary.sample_time.physical_time < "{end_str_rfc}"'
        elif t == 'intraday_heart_rate':
            parent = 'users/me/dataTypes/heart-rate'
            filter_expr = f'heart_rate.sample_time.physical_time >= "{start_str_rfc}" AND heart_rate.sample_time.physical_time < "{end_str_rfc}"'

        if not parent:
            continue

        try:
            points = []
            page_token = None
            while True:
                response = fetcher.service.users().dataTypes().dataPoints().list(
                    parent=parent,
                    filter=filter_expr,
                    pageToken=page_token
                ).execute()
                points.extend(response.get('dataPoints', []))
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
            
            printer.process_and_print(t, points)
        except Exception as e:
            print(f"Error fetching {t}: {e}")

if __name__ == "__main__":
    main()

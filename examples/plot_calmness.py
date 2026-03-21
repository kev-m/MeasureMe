"""
Example: Plotting Calmness
=========================
This script demonstrates the "clean-on-read" approach using the MeasureMe database.
It queries the last month of raw breathing rate, HRV, and resting heart rate data,
applies in-memory curation using fitout helpers, computes a synthetic Calmness Index,
and plots the result.
"""

import os
import sys
import argparse
from datetime import date, timedelta
import numpy as np

# Ensure the measureme src directory is in the Python path
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(base_dir, 'src'))

from measureme.database import get_engine, get_session_maker
from measureme.models import HealthMetric
from sqlalchemy import func

# Import the data cleaning helpers from fitout
import fitout as fo

def get_plotter(interactive=True):
    try:
        import matplotlib
        if interactive:
            matplotlib.use('qtagg')  # Force PyQt6 for interactive UI
        else:
            matplotlib.use('Agg')    # Headless backend for image saving
            
        import matplotlib.pyplot as plt
        from matplotlib.dates import DateFormatter
        return plt, DateFormatter
    except ImportError:
        print("This example requires matplotlib and PyQt6. Please install with: pip install matplotlib PyQt6")
        sys.exit(1)

def extract_aligned_data(metrics, dates, metric_type):
    """Align database entries to a continuous date array, filling missing days with None."""
    array = [None] * len(dates)
    date_map = {d: i for i, d in enumerate(dates)}
    
    for m in metrics:
        if m.metric_type == metric_type:
            # SQLAlchemy might return datetime, we just need the date component
            dt = m.timestamp.date() if hasattr(m.timestamp, 'date') else m.timestamp   
            if dt in date_map:
                array[date_map[dt]] = m.value
    return array

def main():
    parser = argparse.ArgumentParser(description="Query health metrics, clean on the fly, and plot calmness.")
    parser.add_argument('--output', '-o', type=str, help="Save to file instead of opening interactive window.")
    args = parser.parse_args()
    
    plt, DateFormatter = get_plotter(interactive=not bool(args.output))
    
    db_path = os.path.join(base_dir, 'measureme_dev.db')
    engine = get_engine(f"sqlite:///{db_path}")
    Session = get_session_maker(engine)

    print("Connecting to MeasureMe DB...")
    with Session() as session:
        # 1. Find the most recent date we have data for
        max_timestamp = session.query(func.max(HealthMetric.timestamp)).scalar()
        if not max_timestamp:
            print("No data found in the database. Please run ingest_fitout.py first.")
            return
            
        end_date = max_timestamp.date() if hasattr(max_timestamp, 'date') else max_timestamp
        start_date = end_date - timedelta(days=120)
        
        print(f"Querying raw HealthMetric data from {start_date} to {end_date}...")
        # Fetch raw data for the last 30 days
        metrics = session.query(HealthMetric).filter(
            HealthMetric.metric_type.in_(['breathing_rate', 'hrv_rmssd', 'resting_heart_rate']),
            HealthMetric.timestamp >= start_date
        ).all()

    # Generate a contiguous array of dates
    dates = fo.dates_array(start_date, end_date)
    
    # 2. Extract database rows into lists arrays aligned to dates
    breathing_raw = extract_aligned_data(metrics, dates, 'breathing_rate')
    hrv_raw = extract_aligned_data(metrics, dates, 'hrv_rmssd')
    rhr_raw = extract_aligned_data(metrics, dates, 'resting_heart_rate')
    
    # 3. Apply cleaning algorithms (Clean-On-Read feature)
    print("Applying clean-on-read neighbour interpolation and clipping...")
    breathing_data = fo.fill_missing_with_neighbours(breathing_raw)
    hrv_data = fo.fill_missing_with_neighbours(hrv_raw)
    rhr_data = fo.fill_missing_with_neighbours(rhr_raw)
    
    # Replace specific buggy outliers
    breathing_data = fo.fix_invalid_data_points(breathing_data, 10, 20)
    hrv_data = fo.fix_invalid_data_points(hrv_data, 20, 50)
    rhr_data = fo.fix_invalid_data_points(rhr_data, 46, 54)
    
    # Edge case handler: If there were missing arrays right at index 0 or -1, fill_missing_with_neighbours 
    # leaves them as None. We provide a rudimentary fallback so arrays aren't broken.
    if None in rhr_data or None in breathing_data or None in hrv_data:
        print("Warning: Missing values at array boundaries preventing full interpolation.")
        breathing_data = [x if x is not None else 15.0 for x in breathing_data]
        hrv_data = [x if x is not None else 35.0 for x in hrv_data]
        rhr_data = [x if x is not None else 50.0 for x in rhr_data]

    # 4. Create the Derived Calmness Metric
    print("Calculating Calmness Index...")
    dates_array = np.asarray(dates)
    breathing_arr = np.array(breathing_data).astype(float)
    hrv_arr = np.array(hrv_data).astype(float)
    rhr_arr = np.array(rhr_data).astype(float)
    
    # Equation: 100 - (RHR/2 + breathing rate*2 - HRV)
    calmness_index = 100 - (rhr_arr / 2. + breathing_arr * 2. - hrv_arr)
    
    # 5. Plotting
    plt.figure(figsize=(10, 6))
    plt.plot(dates_array, calmness_index, marker='o', linestyle='-', color='b')
    plt.xlabel('Date')
    plt.ylabel('Calmness Index')
    plt.title('Calmness Index Over Time (MeasureMe Data)')
    plt.ylim(60, 95)  # Set the user-defined y-range
    plt.grid(True)
    
    plt.gca().xaxis.set_major_formatter(DateFormatter("%Y-%m-%d"))
    plt.xticks(rotation=45)
    plt.tight_layout()  

    # Fit a 4th order polynomial to the calmness index data
    dates_axis = np.arange(len(dates_array))
    polynomial_coefficients = np.polyfit(dates_axis, calmness_index, 4)
    polynomial = np.poly1d(polynomial_coefficients)
    fitted_calmness_index = polynomial(dates_axis)

    # Plot the fitted polynomial
    plt.plot(dates_array, fitted_calmness_index, linestyle='--', color='r', label='4th Order Polynomial Fit')
    plt.legend()
    
    if args.output:
        plt.savefig(args.output)
        print(f"Plot saved to {args.output}")
    else:
        plt.show()

if __name__ == "__main__":
    main()

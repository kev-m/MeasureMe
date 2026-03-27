"""
Example: Plotting Metrics
=========================
This script demonstrates querying explicit health metrics (Resting Heart Rate
and Heart Rate Variability) from the MeasureMe database, and plotting them 
together over time using Matplotlib.

Requirements:
    pip install matplotlib
"""

import os
import sys
import argparse

# Ensure the measureme src directory is in the Python path
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(base_dir, '..', 'src'))

from measureme.database import get_engine, get_session_maker
from measureme.models import HealthMetric

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

def main():
    parser = argparse.ArgumentParser(description="Query HRV and RHR metrics, and plot them over time.")
    parser.add_argument('--output', '-o', type=str, help="Optional file path to save the plot as an image (e.g. plot.png). This suppresses the interactive window.")
    args = parser.parse_args()
    
    plt, DateFormatter = get_plotter(interactive=not bool(args.output))
    
    # Locate the SQLite database created by ingest_fitout.py
    db_path = os.path.join(base_dir, 'measureme_dev.db')
    db_url = f"sqlite:///{db_path}"
    
    print(f"Connecting to MeasureMe DB: {db_url}")
    
    engine = get_engine(db_url)
    Session = get_session_maker(engine)

    with Session() as session:
        # Fetch ordered historical metrics for HRV & RHR
        metrics = session.query(HealthMetric)\
            .filter(HealthMetric.metric_type.in_(['hrv_rmssd', 'resting_heart_rate']))\
            .order_by(HealthMetric.timestamp.asc()).all()

    dates_hrv = []
    hrv_values = []
    
    dates_rhr = []
    rhr_values = []

    for m in metrics:
        if m.metric_type == 'hrv_rmssd':
            dates_hrv.append(m.timestamp)
            hrv_values.append(m.value)
        elif m.metric_type == 'resting_heart_rate':
            dates_rhr.append(m.timestamp)
            rhr_values.append(m.value)

    if not dates_hrv and not dates_rhr:
        print("No HRV or Resting Heart Rate data found in the database. Run ingest_fitout.py first.")
        return

    # Create the Plot
    fig, ax1 = plt.subplots(figsize=(10, 6))

    color = 'tab:red'
    ax1.set_xlabel('Date')
    ax1.set_ylabel('Resting Heart Rate (bpm)', color=color)
    ax1.plot(dates_rhr, rhr_values, color=color, marker='o', linestyle='-', alpha=0.6, label='RHR')
    ax1.tick_params(axis='y', labelcolor=color)

    # instantiate a second axes that shares the same x-axis
    ax2 = ax1.twinx()  
    color = 'tab:blue'
    ax2.set_ylabel('HRV (ms)', color=color)  
    ax2.plot(dates_hrv, hrv_values, color=color, marker='x', linestyle='-', alpha=0.6, label='HRV')
    ax2.tick_params(axis='y', labelcolor=color)

    plt.title('Resting Heart Rate & HRV Over Time (MeasureMe)')
    
    # Prettify the x-axis dates
    ax1.xaxis.set_major_formatter(DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()

    fig.tight_layout()  # Ensure labels don't get clipped
    
    if args.output:
        fig.savefig(args.output)
        print(f"Plotting complete. Saved image to: {args.output}")
    else:
        print("Plotting complete. Check the opened chart window.")
        plt.show()

if __name__ == "__main__":
    main()

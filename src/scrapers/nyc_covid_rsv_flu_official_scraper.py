#!/usr/bin/env python3
"""
NYC Respiratory Illness Data Scraper
Data source: https://github.com/nychealth/respiratory-illness-data
"""

import pandas as pd
from datetime import datetime
import json
import os

class NYCRespiratoryDataScraper:
    
    def __init__(self):
        self.base_url = "https://raw.githubusercontent.com/nychealth/respiratory-illness-data/main/data"
        self.data_files = {
            'emergency_dept': 'emergencyDeptData.csv',
        }
    
    def get_emergency_dept_data(self):
        """Get emergency department visit data."""
        url = f"{self.base_url}/{self.data_files['emergency_dept']}"
        
        try:
            df = pd.read_csv(url)
            print(f"Downloaded {len(df)} records ({df['date'].min()} to {df['date'].max()})")
            return df
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    def filter_by_disease(self, df, disease='COVID-19'):
        """Filter data for specific disease."""
        return df[df['metric'].str.contains(disease, case=False)]
    
    def filter_by_date(self, df, days_back=30):
        """Filter to recent data."""
        df['date'] = pd.to_datetime(df['date'])
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=days_back)
        return df[df['date'] >= cutoff]
    
    def filter_by_borough(self, df, borough='Overall'):
        """Filter by NYC borough."""
        return df[df['submetric'] == borough]
    
    def save_to_postgres_format(self, df, filename='respiratory_data.csv'):
        """Save in format ready for PostgreSQL/TimescaleDB."""
        df['date'] = pd.to_datetime(df['date'])
        df['scraped_at'] = datetime.now()
        df.to_csv(filename, index=False)
        print(f"Saved to {filename}")
    
    def get_latest_values(self, df):
        """Get the most recent value for each metric/submetric combination."""
        df['date'] = pd.to_datetime(df['date'])
        return df.loc[df.groupby(['metric', 'submetric'])['date'].idxmax()]


def main():
    """Demo usage."""
    print("NYC Respiratory Illness Data Scraper\n")
    
    scraper = NYCRespiratoryDataScraper()
    df = scraper.get_emergency_dept_data()
    
    if df is None:
        return
    
    print(f"Total records: {len(df)}\n")
    
    # Save last 90 days
    recent_90 = scraper.filter_by_date(df, days_back=90)
    #scraper.save_to_postgres_format(recent_90, 'respiratory_data_90days.csv')

    output_dir = "data/nyc_covid"
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.join(output_dir,"respiratory_data_90days.json")
    with open(filename, 'w') as f:
        json.dump(recent_90.to_dict(orient='records'), f, indent=2, default=str)
    print("Saved to respiratory_data_90days.json")
    
    # Show latest values for key metrics
    latest = scraper.get_latest_values(df)
    key_metrics = ['COVID-19 visits', 'Influenza visits', 'RSV visits', 'Respiratory illness visits']
    
    print("\nLatest values:")
    for metric in key_metrics:
        metric_data = latest[(latest['metric'] == metric) & (latest['submetric'] == 'Overall')]
        if not metric_data.empty:
            row = metric_data.iloc[0]
            print(f"  {metric}: {row['value']}% (as of {row['date'].date()})")
    
    print("\nData ready for pipeline integration.")


if __name__ == '__main__':
    main()
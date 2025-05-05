import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import pydeck as pdk
import requests
import os
import re
from dotenv import load_dotenv
import io
from fpdf import FPDF
import base64
import uuid

# Load environment variables
load_dotenv()
OPENCAGE_API_KEY = os.getenv('OPENCAGE_API_KEY')

# Configure page
st.set_page_config(
    page_title="Union App Metrics Dashboard",
    page_icon=r"./your_image.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for the dashboard
st.markdown("""
<style>
    .main {
        background-color: #f8f9fa;
    }
    .stMetric {
        background-color: white;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stMetric label, .stMetric div {
        color: black !important;
    }
    .stPlotlyChart, .stPydeckChart아이테크놀로지 {
        background-color: white;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

PASSENGERS_FILE_PATH = r"./PASSENGERS.xlsx"
DRIVERS_FILE_PATH = r"./DRIVERS.xlsx"
DATA_FILE_PATH = r"./BEER.xlsx"
TRANSACTIONS_FILE_PATH = r"./TRANSACTIONS.xlsx"
UNION_STAFF_FILE_PATH = r"./UNION STAFF.xlsx"

# Function to extract UGX amounts from any column
def extract_ugx_amount(value):
    try:
        if pd.isna(value):
            return 0.0
        amounts = re.findall(r'UGX\s*([\d,]+)', str(value))
        if amounts:
            return sum(float(amount.replace(',', '')) for amount in amounts)
        return float(str(value).replace(',', '')) if str(value).replace(',', '').isdigit() else 0.0
    except:
        return 0.0

# Function to load passengers data with date filtering
def load_passengers_data(date_range=None):
    try:
        df = pd.read_excel(PASSENGERS_FILE_PATH)
        df['Created'] = pd.to_datetime(df['Created'], errors='coerce')

        if date_range and len(date_range) == 2:
            start_date, end_date = date_range
            df = df[(df['Created'].dt.date >= start_date) &
                    (df['Created'].dt.date <= end_date)]
        return df
    except Exception as e:
        st.error(f"Error loading passengers data: {str(e)}")
        return pd.DataFrame()

# Function to load drivers data with date filtering
def load_drivers_data(date_range=None):
    try:
        df = pd.read_excel(DRIVERS_FILE_PATH)
        df['Created'] = pd.to_datetime(df['Created'], errors='coerce')

        if date_range and len(date_range) == 2:
            start_date, end_date = date_range
            df = df[(df['Created'].dt.date >= start_date) &
                    (df['Created'].dt.date <= end_date)]
        return df
    except Exception as e:
        st.error(f"Error loading drivers data: {str(e)}")
        return pd.DataFrame()

# Function to load and merge transactions data
def load_transactions_data():
    try:
        transactions_df = pd.read_excel(TRANSACTIONS_FILE_PATH)
        
        if 'Company Amt (UGX)' in transactions_df.columns:
            transactions_df['Company Commission Cleaned'] = transactions_df['Company Amt (UGX)'].apply(extract_ugx_amount)
        else:
            st.warning("No 'Company Amt (UGX)' column found in transactions data")
            transactions_df['Company Commission Cleaned'] = 0.0
            
        if 'Pay Mode' in transactions_df.columns:
            transactions_df['Pay Mode'] = transactions_df['Pay Mode'].fillna('Unknown')
        else:
            st.warning("No 'Pay Mode' column found in transactions data")
            transactions_df['Pay Mode'] = 'Unknown'
            
        return transactions_df[['Company Commission Cleaned', 'Pay Mode']]
    except Exception as e:
        st.error(f"Error loading transactions data: {str(e)}")
        return pd.DataFrame()

def load_data():
    try:
        df = pd.read_excel(DATA_FILE_PATH)
        
        transactions_df = load_transactions_data()
        if not transactions_df.empty:
            if 'Company Commission Cleaned' in df.columns and 'Company Commission Cleaned' in transactions_df.columns:
                df['Company Commission Cleaned'] += transactions_df['Company Commission Cleaned']
            elif 'Company Commission Cleaned' not in df.columns:
                df['Company Commission Cleaned'] = transactions_df['Company Commission Cleaned']
                
            if 'Pay Mode' not in df.columns:
                df['Pay Mode'] = transactions_df['Pay Mode']

        df['Trip Date'] = pd.to_datetime(df['Trip Date'], errors='coerce')
        df['Trip Hour'] = df['Trip Date'].dt.hour
        df['Day of Week'] = df['Trip Date'].dt.day_name()
        df['Month'] = df['Trip Date'].dt.month_name()

        if 'Trip Pay Amount' in df.columns:
            df['Trip Pay Amount Cleaned'] = df['Trip Pay Amount'].apply(extract_ugx_amount)
        else:
            st.warning("No 'Trip Pay Amount' column found - creating placeholder")
            df['Trip Pay Amount Cleaned'] = 0.0

        df['Distance'] = pd.to_numeric(df['Trip Distance (KM/Mi)'], errors='coerce').fillna(0)

        if 'Company Commission Cleaned' not in df.columns:
            st.warning("No company commission data found - creating placeholder")
            df['Company Commission Cleaned'] = 0.0

        if 'Pay Mode' not in df.columns:
            st.warning("No 'Pay Mode' column found - adding placeholder")
            df['Pay Mode'] = 'Unknown'

        return df

    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return pd.DataFrame()

# Define metrics functions
def passenger_metrics(df_passengers):
    try:
        app_downloads = len(df_passengers) if not df_passengers.empty else 0
        passenger_wallet_balance = df_passengers['Wallet Balance'].sum() if 'Wallet Balance' in df_passengers.columns else 0.0
        return app_downloads, passenger_wallet_balance
    except Exception as e:
        st.error(f"Error in passenger metrics: {str(e)}")
        return 0, 0.0

def driver_metrics(df_drivers):
    try:
        riders_onboarded = len(df_drivers) if not df_drivers.empty else 0
        driver_wallet_balance = df_drivers['Wallet Balance'].sum() if 'Wallet Balance' in df_drivers.columns else 0.0
        commission_owed = df_drivers['Commission Owed'].sum() if 'Commission Owed' in df_drivers.columns else 0.0
        return riders_onboarded, driver_wallet_balance, commission_owed
    except Exception as e:
        st.error(f"Error in driver metrics: {str(e)}")
        return 0, 0.0, 0.0

def calculate_driver_retention_rate(riders_onboarded, app_downloads, unique_drivers):
    try:
        retention_rate = (unique_drivers / riders_onboarded * 100) if riders_onboarded > 0 else 0.0
        passenger_ratio = (app_downloads / unique_drivers) if unique_drivers > 0 else 0.0
        return retention_rate, passenger_ratio
    except Exception as e:
        st.error(f"Error calculating retention rate: {str(e)}")
        return 0.0, 0.0

# Define other required functions
def calculate_cancellation_rate(df):
    try:
        if 'Trip Status' not in df.columns:
            return None
        total_trips = len(df)
        cancelled_trips = len(df[df['Trip Status'].str.contains('Cancel', case=False, na=False)])
        return (cancelled_trips / total_trips * 100) if total_trips > 0 else 0.0
    except:
        return None

def calculate_passenger_search_timeout(df):
    try:
        if 'Trip Status' not in df.columns:
            return None
        total_trips = len(df)
        timeout_trips = len(df[df['Trip Status'].str.contains('Timeout', case=False, na=False)])
        return (timeout_trips / total_trips * 100) if total_trips > 0 else 0.0
    except:
        return None

def completed_vs_cancelled_daily(df):
    try:
        if 'Trip Status' not in df.columns or 'Trip Date' not in df.columns:
            return None
        status_df = df.groupby([df['Trip Date'].dt.date, 'Trip Status']).size().unstack(fill_value=0)
        fig = go.Figure()
        for status in status_df.columns:
            fig.add_trace(go.Scatter(
                x=status_df.index,
                y=status_df[status],
                name=status,
                mode='lines+markers'
            ))
        fig.update_layout(
            title="Daily Trip Status Breakdown",
            xaxis_title="Date",
            yaxis_title="Number of Trips",
            template="plotly_white"
        )
        return fig
    except:
        return None

def trips_per_driver(df):
    try:
        if 'Driver' not in df.columns:
            st.metric("Trips per Driver", "N/A")
            return
        trips_by_driver = df.groupby('Driver').size()
        avg_trips = trips_by_driver.mean() if not trips_by_driver.empty else 0
        st.metric("Avg. Trips per Driver", f"{avg_trips:.1f}")
    except Exception as e:
        st.error(f"Error in trips per driver: {str(e)}")

def total_trips_by_status(df):
    try:
        if 'Trip Status' not in df.columns:
            return
        status_counts = df['Trip Status'].value_counts()
        fig = px.pie(
            values=status_counts.values,
            names=status_counts.index,
            title="Trip Status Distribution"
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in total trips by status: {str(e)}")

def total_distance_covered(df):
    try:
        if 'Distance' not in df.columns:
            return
        total_distance = df['Distance'].sum()
        st.metric("Total Distance Covered", f"{total_distance:,.0f} km")
    except Exception as e:
        st.error(f"Error in total distance covered: {str(e)}")

def revenue_by_day(df):
    try:
        if 'Trip Pay Amount Cleaned' not in df.columns or 'Trip Date' not in df.columns:
            return
        daily_revenue = df.groupby(df['Trip Date'].dt.date)['Trip Pay Amount Cleaned'].sum()
        fig = px.line(
            x=daily_revenue.index,
            y=daily_revenue.values,
            title="Daily Revenue Trend",
            labels={'x': 'Date', 'y': 'Revenue (UGX)'}
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in revenue by day: {str(e)}")

def avg_revenue_per_trip(df):
    try:
        if 'Trip Pay Amount Cleaned' not in df.columns:
            return
        avg_revenue = df['Trip Pay Amount Cleaned'].mean()
        st.metric("Avg. Revenue per Trip", f"{avg_revenue:,.0f} UGX")
    except Exception as e:
        st.error(f"Error in avg revenue per trip: {str(e)}")

def total_commission(df):
    try:
        if 'Company Commission Cleaned' not in df.columns:
            st.metric("Total Commission", "N/A")
            return
        total_comm = df['Company Commission Cleaned'].sum()
        st.metric("Total Commission", f"{total_comm:,.0f} UGX")
    except Exception as e:
        st.error(f"Error in total commission: {str(e)}")

def gross_profit(df):
    try:
        if 'Trip Pay Amount Cleaned' not in df.columns or 'Company Commission Cleaned' not in df.columns:
            return
        gross_profit = df['Company Commission Cleaned'].sum()
        st.metric("Gross Profit", f"{gross_profit:,.0f} UGX")
    except Exception as e:
        st.error(f"Error in gross profit: {str(e)}")

def avg_commission_per_trip(df):
    try:
        if 'Company Commission Cleaned' not in df.columns:
            return
        avg_comm = df['Company Commission Cleaned'].mean()
        st.metric("Avg. Commission per Trip", f"{avg_comm:,.0f} UGX")
    except Exception as e:
        st.error(f"Error in avg commission per trip: {str(e)}")

def revenue_per_driver(df):
    try:
        if 'Driver' not in df.columns or 'Trip Pay Amount Cleaned' not in df.columns:
            return
        revenue_by_driver = df.groupby('Driver')['Trip Pay Amount Cleaned'].sum()
        avg_revenue = revenue_by_driver.mean() if not revenue_by_driver.empty else 0
        st.metric("Avg. Revenue per Driver", f"{avg_revenue:,.0f} UGX")
    except Exception as e:
        st.error(f"Error in revenue per driver: {str(e)}")

def driver_earnings_per_trip(df):
    try:
        if 'Trip Pay Amount Cleaned' not in df.columns or 'Company Commission Cleaned' not in df.columns:
            return
        df['Driver Earnings'] = df['Trip Pay Amount Cleaned'] - df['Company Commission Cleaned']
        avg_earnings = df['Driver Earnings'].mean()
        st.metric("Avg. Driver Earnings per Trip", f"{avg_earnings:,.0f} UGX")
    except Exception as e:
        st.error(f"Error in driver earnings per trip: {str(e)}")

def fare_per_km(df):
    try:
        if 'Trip Pay Amount Cleaned' not in df.columns or 'Distance' not in df.columns:
            return
        df['Fare per KM'] = df['Trip Pay Amount Cleaned'] / df['Distance'].replace(0, 1)
        avg_fare_per_km = df['Fare per KM'].mean()
        st.metric("Avg. Fare per KM", f"{avg_fare_per_km:,.0f} UGX")
    except Exception as e:
        st.error(f"Error in fare per km: {str(e)}")

def revenue_share(df):
    try:
        if 'Trip Pay Amount Cleaned' not in df.columns or 'Company Commission Cleaned' not in df.columns:
            return
        total_revenue = df['Trip Pay Amount Cleaned'].sum()
        total_commission = df['Company Commission Cleaned'].sum()
        revenue_share = (total_commission / total_revenue * 100) if total_revenue > 0 else 0
        st.metric("Revenue Share", f"{revenue_share:.1f}%")
    except Exception as e:
        st.error(f"Error in revenue share: {str(e)}")

def total_trips_by_type(df):
    try:
        if 'Trip Type' not in df.columns:
            return
        type_counts = df['Trip Type'].value_counts()
        fig = px.bar(
            x=type_counts.index,
            y=type_counts.values,
            title="Trips by Type",
            labels={'x': 'Trip Type', 'y': 'Number of Trips'}
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in total trips by type: {str(e)}")

def payment_method_revenue(df):
    try:
        if 'Pay Mode' not in df.columns or 'Trip Pay Amount Cleaned' not in df.columns:
            return
        revenue_by_payment = df.groupby('Pay Mode')['Trip Pay Amount Cleaned'].sum()
        fig = px.pie(
            values=revenue_by_payment.values,
            names=revenue_by_payment.index,
            title="Revenue by Payment Method"
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in payment method revenue: {str(e)}")

def distance_vs_revenue_scatter(df):
    try:
        if 'Distance' not in df.columns or 'Trip Pay Amount Cleaned' not in df.columns:
            return
        fig = px.scatter(
            df,
            x='Distance',
            y='Trip Pay Amount Cleaned',
            title="Distance vs Revenue",
            labels={'Distance': 'Distance (km)', 'Trip Pay Amount Cleaned': 'Revenue (UGX)'}
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in distance vs revenue scatter: {str(e)}")

def weekday_vs_weekend_analysis(df):
    try:
        if 'Day of Week' not in df.columns or 'Trip Pay Amount Cleaned' not in df.columns:
            return
        df['Is Weekend'] = df['Day of Week'].isin(['Saturday', 'Sunday'])
        revenue_by_period = df.groupby('Is Weekend')['Trip Pay Amount Cleaned'].sum()
        fig = px.bar(
            x=['Weekday', 'Weekend'],
            y=revenue_by_period.values,
            title=" kwest vs Weekend Revenue",
            labels={'x': 'Period', 'y': 'Revenue (UGX)'}
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in weekday vs weekend analysis: {str(e)}")

def unique_driver_count(df):
    try:
        if 'Driver' not in df.columns:
            return
        unique_drivers = df['Driver'].nunique()
        st.metric("Unique Drivers", unique_drivers)
    except Exception as e:
        st.error(f"Error in unique driver count: {str(e)}")

def top_drivers_by_revenue(df):
    try:
        if 'Driver' not in df.columns or 'Trip Pay Amount Cleaned' not in df.columns:
            return
        top_drivers = df.groupby('Driver')['Trip Pay Amount Cleaned'].sum().nlargest(5)
        fig = px.bar(
            x=top_drivers.values,
            y=top_drivers.index,
            orientation='h',
            title="Top 5 Drivers by Revenue",
            labels={'x': 'Revenue (UGX)', 'y': 'Driver'}
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in top drivers by revenue: {str(e)}")

def driver_performance_comparison(df):
    try:
        if 'Driver' not in df.columns:
            return
        driver_stats = df.groupby('Driver').agg({
            'Trip Pay Amount Cleaned': 'sum',
            'Distance': 'sum',
            'Trip Date': 'count'
        }).rename(columns={'Trip Date': 'Trip Count'})
        fig = px.scatter(
            driver_stats,
            x='Trip Count',
            y='Trip Pay Amount Cleaned',
            size='Distance',
            hover_name=driver_stats.index,
            title="Driver Performance Comparison",
            labels={'Trip Count': 'Number of Trips', 'Trip Pay Amount Cleaned': 'Revenue (UGX)'}
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in driver performance comparison: {str(e)}")

def passenger_insights(df):
    try:
        if 'Passenger' not in df.columns:
            return
        passenger_trips = df.groupby('Passenger').size().value_counts()
        fig = px.bar(
            x=passenger_trips.index,
            y=passenger_trips.values,
            title="Passenger Trip Frequency",
            labels={'x': 'Number of Trips', 'y': 'Number of Passengers'}
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in passenger insights: {str(e)}")

def passenger_value_segmentation(df):
    try:
        if 'Passenger' not in df.columns or 'Trip Pay Amount Cleaned' not in df.columns:
            return
        passenger_revenue = df.groupby('Passenger')['Trip Pay Amount Cleaned'].sum()
        bins = pd.qcut(passenger_revenue, q=3, labels=['Low', 'Medium', 'High'], duplicates='drop')
        segment_counts = bins.value_counts()
        fig = px.pie(
            values=segment_counts.values,
            names=segment_counts.index,
            title="Passenger Value Segmentation"
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in passenger value segmentation: {str(e)}")

def top_10_drivers_by_earnings(df):
    try:
        if 'Driver' not in df.columns or 'Trip Pay Amount Cleaned' not in df.columns or 'Company Commission Cleaned' not in df.columns:
            return
        df['Driver Earnings'] = df['Trip Pay Amount Cleaned'] - df['Company Commission Cleaned']
        top_drivers = df.groupby('Driver')['Driver Earnings'].sum().nlargest(10)
        fig = px.bar(
            x=top_drivers.values,
            y=top_drivers.index,
            orientation='h',
            title="Top 10 Drivers by Earnings",
            labels={'x': 'Earnings (UGX)', 'y': 'Driver'}
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in top 10 drivers by earnings: {str(e)}")

def get_completed_trips_by_union_passengers(df, union_staff_names):
    try:
        if 'Passenger' not in df.columns or 'Trip Status' not in df.columns:
            return pd.DataFrame()
        staff_trips = df[
            (df['Passenger'].isin(union_staff_names)) &
            (df['Trip Status'] == 'Job Completed')
        ][['Passenger', 'Trip Date', 'Trip Pay Amount Cleaned', 'Distance']]
        return staff_trips
    except Exception as e:
        st.error(f"Error in get completed trips by union passengers: {str(e)}")
        return pd.DataFrame()

def most_frequent_locations(df):
    try:
        if 'Pickup Location' not in df.columns or 'Dropoff Location' not in df.columns:
            return
        pickup_counts = df['Pickup Location'].value_counts().head(5)
        dropoff_counts = df['Dropoff Location'].value_counts().head(5)
        col1, col2 = st.columns(2)
        with col1:
            fig1 = px.bar(
                x=pickup_counts.values,
                y=pickup_counts.index,
                orientation='h',
                title="Top 5 Pickup Locations",
                labels={'x': 'Number of Trips', 'y': 'Location'}
            )
            st.plotly_chart(fig1, use_container_width=True)
        with col2:
            fig2 = px.bar(
                x=dropoff_counts.values,
                y=dropoff_counts.index,
                orientation='h',
                title="Top 5 Dropoff Locations",
                labels={'x': 'Number of Trips', 'y': 'Location'}
            )
            st.plotly_chart(fig2, use_container_width=True)
    except Exception as e:
        st.error(f"Error in most frequent locations: {str(e)}")

def peak_hours(df):
    try:
        if 'Trip Hour' not in df.columns:
            return
        hour_counts = df['Trip Hour'].value_counts().sort_index()
        fig = px.bar(
            x=hour_counts.index,
            y=hour_counts.values,
            title="Trip Distribution by Hour",
            labels={'x': 'Hour of Day', 'y': 'Number of Trips'}
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in peak hours: {str(e)}")

def trip_status_trends(df):
    try:
        if 'Trip Status' not in df.columns or 'Trip Date' not in df.columns:
            return
        status_trends = df.groupby([df['Trip Date'].dt.date, 'Trip Status']).size().unstack(fill_value=0)
        fig = go.Figure()
        for status in status_trends.columns:
            fig.add_trace(go.Scatter(
                x=status_trends.index,
                y=status_trends[status],
                name=status,
                mode='lines+markers'
            ))
        fig.update_layout(
            title="Trip Status Trends Over Time",
            xaxis_title="Date",
            yaxis_title="Number of Trips",
            template="plotly_white"
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in trip status trends: {str(e)}")

def customer_payment_methods(df):
    try:
        if 'Pay Mode' not in df.columns:
            return
        payment_counts = df['Pay Mode'].value_counts()
        fig = px.pie(
            values=payment_counts.values,
            names=payment_counts.index,
            title="Customer Payment Methods"
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in customer payment methods: {str(e)}")

def get_download_data(df):
    try:
        download_df = df[['Trip Date', 'Trip Status', 'Driver', 'Passenger', 'Trip Pay Amount Cleaned', 'Company Commission Cleaned', 'Distance', 'Pay Mode']].copy()
        download_df['Trip Date'] = download_df['Trip Date'].dt.strftime('%Y-%m-%d')
        return download_df
    except Exception as e:
        st.error(f"Error in get download data: {str(e)}")
        return pd.DataFrame()

def create_metrics_pdf(df, date_range, retention_rate, passenger_ratio, app_downloads, riders_onboarded, passenger_wallet_balance, driver_wallet_balance, commission_owed):
    try:
        class PDF(FPDF):
            def header(self):
                self.set_font('Arial', 'B', 12)
                self.cell(0, 10, 'Union App Metrics Report', 0, 1, 'C')
                self.ln(5)

            def footer(self):
                self.set_y(-15)
                self.set_font('Arial', 'I', 8)
                self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

        pdf = PDF()
        pdf.add_page()
        pdf.set_font('Arial', '', 12)

        # Convert date_range to strings
        start_date_str = date_range[0].strftime('%Y-%m-%d') if date_range and len(date_range) > 0 else 'N/A'
        end_date_str = date_range[1].strftime('%Y-%m-%d') if date_range and len(date_range) > 1 else 'N/A'
        pdf.cell(0, 10, f"Date Range: {start_date_str} to {end_date_str}", 0, 1)
        pdf.ln(5)

        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, "Key Metrics", 0, 1)
        pdf.set_font('Arial', '', 12)
        pdf.cell(0, 10, f"Total Trips: {int(len(df))}", 0, 1)
        pdf.cell(0, 10, f"Completed Trips: {int(len(df[df['Trip Status'] == 'Job Completed']))}", 0, 1)
        pdf.cell(0, 10, f"Total Revenue: {df['Trip Pay Amount Cleaned'].sum():,.0f} UGX", 0, 1)
        pdf.cell(0, 10, f"Total Commission: {df['Company Commission Cleaned'].sum():,.0f} UGX", 0, 1)
        pdf.cell(0, 10, f"Passenger App Downloads: {int(app_downloads)}", 0, 1)
        pdf.cell(0, 10, f"Riders Onboarded: {int(riders_onboarded)}", 0, 1)
        pdf.cell(0, 10, f"Driver Retention Rate: {retention_rate:.1f}%", 0, 1)
        pdf.cell(0, 10, f"Passenger-to-Driver Ratio: {passenger_ratio:.1f}", 0, 1)
        pdf.cell(0, 10, f"Passenger Wallet Balance: {passenger_wallet_balance:,.0f} UGX", 0, 1)
        pdf.cell(0, 10, f"Driver Wallet Balance: {driver_wallet_balance:,.0f} UGX", 0, 1)
        pdf.cell(0, 10, f"Commission Owed: {commission_owed:,.0f} UGX", 0, 1)

        return pdf
    except Exception as e:
        st.error(f"Error in create metrics pdf: {str(e)}")
        return PDF()

def main():
    st.title("Union App Metrics Dashboard")

    try:
        st.cache_data.clear()

        min_date = datetime(2023, 1, 1).date()
        max_date = datetime.now().date()

        try:
            df = load_data()
            if not df.empty and 'Trip Date' in df.columns:
                min_date = df['Trip Date'].min().date()
                max_date = df['Trip Date'].max().date()
        except:
            pass

        date_range = st.sidebar.date_input(
            "Date Range",
            value=[min_date, max_date],
            min_value=min_date,
            max_value=max_date
        )

        df = load_data()
        if len(date_range) == 2:
            df = df[(df['Trip Date'].dt.date >= date_range[0]) &
                    (df['Trip Date'].dt.date <= date_range[1])]

        df_passengers = load_passengers_data(date_range)
        df_drivers = load_drivers_data(date_range)

        if df.empty:
            st.error("No data loaded - please check the backend data file")
            return

        if 'Trip Date' not in df.columns:
            st.error("No 'Trip Date' column found in the data")
            return

        app_downloads, passenger_wallet_balance = passenger_metrics(df_passengers)
        riders_onboarded, driver_wallet_balance, commission_owed = driver_metrics(df_drivers)

        unique_drivers = df['Driver'].nunique() if 'Driver' in df.columns else 0
        retention_rate, passenger_ratio = calculate_driver_retention_rate(
            riders_onboarded, app_downloads, unique_drivers
        )

        st.sidebar.markdown("---")
        st.sidebar.subheader("Export Data")
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            get_download_data(df).to_excel(writer, sheet_name='Dashboard Data', index=False)
        excel_data = output.getvalue()
        st.sidebar.download_button(
            label="📊 Download Full Data (Excel)",
            data=excel_data,
            file_name=f"union_app_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        pdf = create_metrics_pdf(df, date_range, retention_rate, passenger_ratio,
                                 app_downloads, riders_onboarded, passenger_wallet_balance,
                                 driver_wallet_balance, commission_owed)
        pdf_output = pdf.output(dest='S').encode('latin1')
        st.sidebar.download_button(
            label="📄 Download Metrics Report (PDF)",
            data=pdf_output,
            file_name=f"union_app_metrics_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf"
        )

        tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Financial", "User Analysis", "Geographic"])

        with tab1:
            st.header("Trips Overview")

            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Total Requests", len(df))
            with col2:
                completed_trips = len(df[df['Trip Status'] == 'Job Completed'])
                st.metric("Completed Trips", completed_trips)
            with col3:
                st.metric("Avg. Distance", f"{df['Distance'].mean():.1f} km" if 'Distance' in df.columns else "N/A")
            with col4:
                cancellation_rate = calculate_cancellation_rate(df)
                if cancellation_rate is not None:
                    st.metric("Driver Cancellation Rate", f"{cancellation_rate:.1f}%")
                else:
                    st.metric("Driver Cancellation Rate", "N/A")
            with col5:
                timeout_rate = calculate_passenger_search_timeout(df)
                if timeout_rate is not None:
                    st.metric("Passenger Search Timeout", f"{timeout_rate:.1f}%")
                else:
                    st.metric("Passenger Search Timeout", "N/A")

            status_breakdown_fig = completed_vs_cancelled_daily(df)
            if status_breakdown_fig:
                st.plotly_chart(status_breakdown_fig, use_container_width=True)
            else:
                st.warning("Could not generate trip status breakdown chart - missing required data")

            col6, col7, col8 = st.columns(3)
            with col6:
                trips_per_driver(df)
            with col7:
                st.metric("Passenger App Downloads", app_downloads)
            with col8:
                st.metric("Riders Onboarded", riders_onboarded)

            total_trips_by_status(df)
            total_distance_covered(df)
            revenue_by_day(df)
            avg_revenue_per_trip(df)
            total_commission(df)

        with tab2:
            st.header("Financial Performance")

            col1, col2, col3 = st.columns(3)
            with col1:
                total_revenue = df['Trip Pay Amount Cleaned'].sum()
                st.metric("Total Value Of Rides", f"{total_revenue:,.0f} UGX")
            with col2:
                total_commission(df)
            with col3:
                gross_profit(df)

            col4, col5, col6 = st.columns(3)
            with col4:
                st.metric("Passenger Wallet Balance", f"{passenger_wallet_balance:,.0f} UGX")
            with col5:
                st.metric("Driver Wallet Balance", f"{driver_wallet_balance:,.0f} UGX")
            with col6:
                st.metric("Commission Owed", f"{commission_owed:,.0f} UGX")

            col7, col8, col9 = st.columns(3)
            with col7:
                avg_commission_per_trip(df)
            with col8:
                revenue_per_driver(df)
            with col9:
                driver_earnings_per_trip(df)

            col10, col11 = st.columns(2)
            with col10:
                fare_per_km(df)
            with col11:
                revenue_share(df)

            total_trips_by_type(df)
            payment_method_revenue(df)
            distance_vs_revenue_scatter(df)
            weekday_vs_weekend_analysis(df)

        with tab3:
            st.header("User Performance")

            col1, col2, col3 = st.columns(3)
            with col1:
                unique_driver_count(df)
            with col2:
                st.metric("Passenger App Downloads", app_downloads)
            with col3:
                st.metric("Riders Onboarded", riders_onboarded)

            col4, col5 = st.columns(2)
            with col4:
                st.metric("Driver Retention Rate", f"{retention_rate:.1f}%",
                          help="Percentage of onboarded riders who are active drivers")
            with col5:
                st.metric("Passenger-to-Driver Ratio", f"{passenger_ratio:.1f}",
                          help="Number of passengers per active driver")

            top_drivers_by_revenue(df)
            driver_performance_comparison(df)
            passenger_insights(df)
            passenger_value_segmentation(df)
            top_10_drivers_by_earnings(df)

            st.markdown("---")
            st.subheader("Union Staff Trip Completion")

            try:
                if os.path.exists(UNION_STAFF_FILE_PATH):
                    union_staff_df = pd.read_excel(UNION_STAFF_FILE_PATH)
                    if union_staff_df.empty or union_staff_df.shape[1] == 0:
                        st.warning("Union Staff file is empty or does not contain columns.")
                    else:
                        union_staff_names = union_staff_df.iloc[:, 0].dropna().astype(str).tolist()
                        st.metric("Total Union Staff Members", len(union_staff_names))

                        staff_trips_df = get_completed_trips_by_union_passengers(df, union_staff_names)
                        if not staff_trips_df.empty:
                            st.dataframe(staff_trips_df)
                        else:
                            st.info("No matching completed trips found for Union Staff members.")
                else:
                    st.info(f"Union Staff file not found at: {UNION_STAFF_FILE_PATH}")

            except Exception as e:
                st.error(f"Error processing Union Staff file: {e}")

        with tab4:
            st.header("Geographic Analysis")
            most_frequent_locations(df)
            peak_hours(df)
            trip_status_trends(df)
            customer_payment_methods(df)

    except FileNotFoundError:
        st.error("Data file not found. Please ensure the Excel file is placed in the data/ directory.")
    except Exception as e:
        st.error(f"Error: {e}")

if __name__ == "__main__":
    if not os.path.exists("data"):
        os.makedirs("data")
    main()
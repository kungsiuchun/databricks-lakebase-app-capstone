# Databricks notebook source
# DBTITLE 1,Overview
# MAGIC %md
# MAGIC # Ingest Ticker Technical Indicators (Lakebase)
# MAGIC
# MAGIC This notebook fetches technical indicators (SMA, EMA, MACD, RSI) for watchlisted tickers from the Massive API and stores them in Lakebase.
# MAGIC
# MAGIC It:
# MAGIC 1. Reads the `watchlist` table to find tracked ticker symbols
# MAGIC 2. Fetches technical indicators for each ticker from Massive API:
# MAGIC    - **SMA** (Simple Moving Average) - 50-day and 200-day
# MAGIC    - **EMA** (Exponential Moving Average) - 12-day and 26-day
# MAGIC    - **MACD** (Moving Average Convergence/Divergence) - standard 12/26/9
# MAGIC    - **RSI** (Relative Strength Index) - 14-day
# MAGIC 3. Inserts the indicators into the `technical_indicators` table in Lakebase
# MAGIC 4. Respects the free Massive API rate limit (5 requests/minute)
# MAGIC
# MAGIC **Prerequisites:**
# MAGIC - Run `sql/09_setup_technical_indicators_table.sql` to create the table
# MAGIC - Ensure the `watchlist` table exists in Lakebase
# MAGIC - Massive API key stored in Databricks secrets

# COMMAND ----------

# DBTITLE 1,Install required packages
# MAGIC %pip install -q 'databricks-sdk>=0.118.0' psycopg2 requests

# COMMAND ----------

# DBTITLE 1,Restart Python
dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Configuration
# MAGIC %md
# MAGIC ## Configuration
# MAGIC
# MAGIC Widgets allow you to customize table names, API limits, and rate limits without editing the notebook.

# COMMAND ----------

# DBTITLE 1,Setup widgets
dbutils.widgets.text("watchlist_table_name", "watchlist", "Source table (watchlist)")
dbutils.widgets.text("indicators_table_name", "technical_indicators", "Destination table (indicators)")
dbutils.widgets.text("massive_secret_scope", "massive", "Massive API secret scope")
dbutils.widgets.text("massive_secret_key", "api-key", "Massive API secret key")
dbutils.widgets.text("massive_api_base_url", "https://api.massive.com", "Massive API base URL")
dbutils.widgets.text("max_requests_per_minute", "5", "Massive API rate limit (free tier)")
dbutils.widgets.text("data_limit_per_indicator", "100", "Max data points per indicator")

WATCHLIST_TABLE_NAME = dbutils.widgets.get("watchlist_table_name")
INDICATORS_TABLE_NAME = dbutils.widgets.get("indicators_table_name")
MASSIVE_SECRET_SCOPE = dbutils.widgets.get("massive_secret_scope")
MASSIVE_SECRET_KEY = dbutils.widgets.get("massive_secret_key")
MASSIVE_API_BASE_URL = dbutils.widgets.get("massive_api_base_url")
MAX_REQUESTS_PER_MINUTE = int(dbutils.widgets.get("max_requests_per_minute"))
DATA_LIMIT = int(dbutils.widgets.get("data_limit_per_indicator"))

print(f"Configuration:")
print(f"  Source: {WATCHLIST_TABLE_NAME}")
print(f"  Destination: {INDICATORS_TABLE_NAME}")
print(f"  Rate limit: {MAX_REQUESTS_PER_MINUTE} req/min")
print(f"  Data limit: {DATA_LIMIT} points per indicator")

# COMMAND ----------

# DBTITLE 1,Lakebase Connection
# MAGIC %md
# MAGIC ## Resolve Lakebase Connection
# MAGIC
# MAGIC Parse the Lakebase connection URL from Databricks secrets (same pattern as `ingest_ticker_news_embeddings`).

# COMMAND ----------

# DBTITLE 1,Parse Lakebase connection info
import base64
from urllib.parse import urlparse
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

def get_lakebase_url() -> str:
    secret = w.secrets.get_secret(scope="database", key="lakebase-url")
    return base64.b64decode(secret.value).decode("utf-8")

lakebase_url = get_lakebase_url()
parsed = urlparse(lakebase_url)

db_host = parsed.hostname
db_port = parsed.port or 5432
db_name = parsed.path.lstrip('/')
db_user = parsed.username
db_password = parsed.password

print(f"Connection details:")
print(f"  Host: {db_host}:{db_port}")
print(f"  Database: {db_name}")
print(f"  User: {db_user}")

# COMMAND ----------

# DBTITLE 1,Test connection
import psycopg2

print(f"Testing connection to {db_host}:{db_port}/{db_name}")

try:
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
        sslmode='require',
        connect_timeout=10
    )
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {WATCHLIST_TABLE_NAME}")
    count = cursor.fetchone()[0]
    print(f"✅ Connection successful! Found {count} rows in {WATCHLIST_TABLE_NAME}")
    cursor.close()
    conn.close()
except Exception as e:
    import traceback
    print(f"❌ Connection failed: {e}")
    traceback.print_exc()

# COMMAND ----------

# DBTITLE 1,Load MassiveClient
# MAGIC %md
# MAGIC ## Load MassiveClient Module
# MAGIC
# MAGIC Import the `massive_client.py` module which contains the new technical indicator methods.

# COMMAND ----------

# DBTITLE 1,Import massive_client
import sys
import os

# Add parent directory to path to import massive_client
parent_dir = os.path.abspath(os.path.join(os.getcwd(), '../..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from massive_client import MassiveClient

print("✅ MassiveClient imported successfully")
print(f"   Available methods: get_sma, get_ema, get_macd, get_rsi")

# COMMAND ----------

# DBTITLE 1,Fetch Indicators
# MAGIC %md
# MAGIC ## Fetch Technical Indicators
# MAGIC
# MAGIC For each ticker in the watchlist, fetch:
# MAGIC - **SMA**: 50-day and 200-day simple moving averages
# MAGIC - **EMA**: 12-day and 26-day exponential moving averages  
# MAGIC - **MACD**: Moving Average Convergence/Divergence (12/26/9)
# MAGIC - **RSI**: 14-day Relative Strength Index
# MAGIC
# MAGIC Rate limited to stay within the free Massive API tier (5 requests/minute).

# COMMAND ----------

# DBTITLE 1,Get watchlist tickers
def get_watchlist_tickers() -> list[str]:
    """Get distinct, uppercased ticker symbols from the watchlist table."""
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
        sslmode='require'
    )
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT DISTINCT symbol FROM {WATCHLIST_TABLE_NAME} WHERE symbol IS NOT NULL")
        symbols = cursor.fetchall()
        return [row[0].strip().upper() for row in symbols if row[0]]
    finally:
        cursor.close()
        conn.close()

tickers = get_watchlist_tickers()
print(f"Found {len(tickers)} distinct watchlisted tickers: {tickers}")

# COMMAND ----------

# DBTITLE 1,Fetch technical indicators from Massive API
import time
from datetime import datetime
import os

# Set environment variables for MassiveClient
os.environ["MASSIVE_SECRET_SCOPE"] = MASSIVE_SECRET_SCOPE
os.environ["MASSIVE_SECRET_KEY"] = MASSIVE_SECRET_KEY
os.environ["MASSIVE_API_BASE_URL"] = MASSIVE_API_BASE_URL

# Initialize Massive client (it fetches API key from secrets automatically)
client = MassiveClient()

print(f"Fetching technical indicators for {len(tickers)} tickers...")
print(f"Rate limit: {MAX_REQUESTS_PER_MINUTE} requests/minute")
print(f"This will take approximately {len(tickers) * 4 / MAX_REQUESTS_PER_MINUTE:.1f} minutes\n")

# Calculate sleep time between requests
seconds_between_requests = 60.0 / MAX_REQUESTS_PER_MINUTE

all_indicators = []
request_count = 0

for ticker_idx, ticker in enumerate(tickers):
    print(f"[{ticker_idx + 1}/{len(tickers)}] Processing {ticker}...")
    
    # Define indicators to fetch: (method, params, indicator_type)
    indicators_to_fetch = [
        (client.get_sma, {"window": 50, "limit": DATA_LIMIT}, "SMA", {"window_size": 50}),
        (client.get_sma, {"window": 200, "limit": DATA_LIMIT}, "SMA", {"window_size": 200}),
        (client.get_ema, {"window": 12, "limit": DATA_LIMIT}, "EMA", {"window_size": 12}),
        (client.get_ema, {"window": 26, "limit": DATA_LIMIT}, "EMA", {"window_size": 26}),
        (client.get_macd, {"limit": DATA_LIMIT}, "MACD", {"short_window": 12, "long_window": 26, "signal_window": 9}),
        (client.get_rsi, {"window": 14, "limit": DATA_LIMIT}, "RSI", {"window_size": 14}),
    ]
    
    for method, params, indicator_type, metadata in indicators_to_fetch:
        # Rate limiting
        if request_count > 0:
            time.sleep(seconds_between_requests)
        
        try:
            response = method(ticker, **params)
            
            if response.get("status") == "OK" and "results" in response:
                values = response["results"].get("values", [])
                
                for item in values:
                    # Base row structure
                    row = {
                        "ticker": ticker,
                        "indicator_type": indicator_type,
                        "timestamp_ms": item.get("timestamp"),
                        "value": item.get("value"),
                        "series_type": "close",  # Default from API
                        "timespan": "day",       # Default from API
                    }
                    
                    # Add metadata based on indicator type
                    if indicator_type == "MACD":
                        row["short_window"] = metadata["short_window"]
                        row["long_window"] = metadata["long_window"]
                        row["signal_window"] = metadata["signal_window"]
                        row["signal"] = item.get("signal")
                        row["histogram"] = item.get("histogram")
                        # Use short_window as window_size for MACD (required by PRIMARY KEY)
                        row["window_size"] = metadata["short_window"]
                    else:
                        row["window_size"] = metadata.get("window_size")
                        row["short_window"] = None
                        row["long_window"] = None
                        row["signal_window"] = None
                        row["signal"] = None
                        row["histogram"] = None
                    
                    all_indicators.append(row)
                
                print(f"  {indicator_type} ({metadata}): {len(values)} data points")
            else:
                print(f"  {indicator_type} ({metadata}): No data (status: {response.get('status', 'UNKNOWN')})")
            
            request_count += 1
            
        except Exception as e:
            print(f"  {indicator_type} ({metadata}): Error - {e}")
            continue

print(f"\n✅ Collected {len(all_indicators)} indicator data points from {request_count} API requests")
print(f"Ready to insert into {INDICATORS_TABLE_NAME}")

# COMMAND ----------

# DBTITLE 1,Insert into Lakebase
# MAGIC %md
# MAGIC ## Insert Technical Indicators into Lakebase
# MAGIC
# MAGIC Batch insert using psycopg2's `executemany` for throughput. Uses `ON CONFLICT DO NOTHING` for automatic deduplication based on the composite primary key (ticker, indicator_type, timestamp_ms, window_size).

# COMMAND ----------

# DBTITLE 1,Insert indicators using psycopg2
import psycopg2
from psycopg2.extras import execute_values

if len(all_indicators) > 0:
    print(f"Inserting {len(all_indicators)} indicators into {INDICATORS_TABLE_NAME}...")
    
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
        sslmode='require'
    )
    
    try:
        cursor = conn.cursor()
        
        # Prepare data tuples for batch insert
        insert_data = [
            (
                row['ticker'],
                row['indicator_type'],
                row['timestamp_ms'],
                row['window_size'],
                row['short_window'],
                row['long_window'],
                row['signal_window'],
                row['series_type'],
                row['timespan'],
                row['value'],
                row['signal'],
                row['histogram']
            )
            for row in all_indicators
        ]
        
        # Batch insert with ON CONFLICT DO NOTHING for deduplication
        insert_sql = f"""
            INSERT INTO {INDICATORS_TABLE_NAME} (
                ticker, indicator_type, timestamp_ms, window_size,
                short_window, long_window, signal_window,
                series_type, timespan, value, signal, histogram
            ) VALUES %s
            ON CONFLICT (ticker, indicator_type, timestamp_ms, window_size) DO NOTHING
        """
        
        # execute_values is much faster than individual INSERTs
        execute_values(cursor, insert_sql, insert_data, page_size=100)
        
        conn.commit()
        inserted_count = cursor.rowcount
        print(f"✅ Successfully inserted {inserted_count} new indicator data points")
        print(f"   (Duplicates were skipped via ON CONFLICT DO NOTHING)")
        
        # Show summary by indicator type
        cursor.execute(f"""
            SELECT indicator_type, COUNT(*) as count
            FROM {INDICATORS_TABLE_NAME}
            GROUP BY indicator_type
            ORDER BY indicator_type
        """)
        summary = cursor.fetchall()
        print(f"\nCurrent table summary:")
        for ind_type, count in summary:
            print(f"  {ind_type}: {count} data points")
        
    finally:
        cursor.close()
        conn.close()
else:
    print("No indicators to insert.")

print(f"\n✅ Technical indicators ingestion complete!")

# COMMAND ----------

# DBTITLE 1,Summary
# MAGIC %md
# MAGIC ## Summary
# MAGIC
# MAGIC This notebook has:
# MAGIC
# MAGIC 1. ✅ Connected to Lakebase using the same secret pattern as other notebooks
# MAGIC 2. ✅ Fetched technical indicators (SMA, EMA, MACD, RSI) for all watchlisted tickers
# MAGIC 3. ✅ Respected the Massive API free tier rate limit (5 requests/minute)
# MAGIC 4. ✅ Inserted all data into the `technical_indicators` table with automatic deduplication
# MAGIC
# MAGIC ### Next Steps
# MAGIC
# MAGIC - **Query the data**: Use the `technical_indicators` table in your Lakebase queries
# MAGIC - **Schedule this notebook**: Run it on a schedule (e.g., daily) to keep indicators up-to-date
# MAGIC - **Visualize trends**: Build dashboards showing indicator trends over time
# MAGIC - **Trading signals**: Use MACD crossovers, RSI overbought/oversold levels, SMA/EMA crosses
# MAGIC
# MAGIC ### Example Query
# MAGIC
# MAGIC ```sql
# MAGIC -- Get latest RSI values for all tickers
# MAGIC SELECT 
# MAGIC     ticker,
# MAGIC     value as rsi,
# MAGIC     timestamp_utc,
# MAGIC     CASE 
# MAGIC         WHEN value > 70 THEN 'Overbought'
# MAGIC         WHEN value < 30 THEN 'Oversold'
# MAGIC         ELSE 'Neutral'
# MAGIC     END as signal
# MAGIC FROM technical_indicators
# MAGIC WHERE indicator_type = 'RSI'
# MAGIC   AND window_size = 14
# MAGIC ORDER BY ticker, timestamp_ms DESC;
# MAGIC ```

# COMMAND ----------


# Databricks notebook source
# MAGIC %md
# MAGIC # Ingest Ticker Data (Price History, Details, Metrics)
# MAGIC
# MAGIC This notebook:
# MAGIC 1. Reads the `watchlist` table in Lakebase to find which ticker symbols are currently being tracked
# MAGIC 2. Fetches data for those tickers from the Massive API:
# MAGIC    - **Ticker Details** - company info (name, description, market cap, etc.)
# MAGIC    - **Price History** - last 30 days of OHLCV data
# MAGIC    - **Ticker Metrics** - current price, volume, and market data
# MAGIC 3. Upserts the results into three Lakebase tables:
# MAGIC    - `ticker_details`
# MAGIC    - `price_history`
# MAGIC    - `ticker_metrics`
# MAGIC
# MAGIC **Rate Limiting**: The free Massive API tier has strict rate limits (5 requests/minute). This notebook includes delays between API calls to stay within quota.

# COMMAND ----------

# DBTITLE 1,Install required packages
# MAGIC %pip uninstall -y psycopg2 psycopg2-binary
# MAGIC %pip install -q 'databricks-sdk>=0.118.0' requests pandas

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Config
# MAGIC
# MAGIC Widgets let you override the source/destination table names and API settings without editing the notebook - useful when running this as a scheduled Databricks Job.

# COMMAND ----------

# DBTITLE 1,Configuration widgets
dbutils.widgets.text("watchlist_table_name", "watchlist", "Source table (watchlist symbols)")
dbutils.widgets.text("details_table_name", "ticker_details", "Destination table (company details)")
dbutils.widgets.text("history_table_name", "price_history", "Destination table (price history)")
dbutils.widgets.text("metrics_table_name", "ticker_metrics", "Destination table (current metrics)")
dbutils.widgets.text("massive_secret_scope", "massive", "Massive API secret scope")
dbutils.widgets.text("massive_secret_key", "api-key", "Massive API secret key")
dbutils.widgets.text("massive_api_base_url", "https://api.massive.com", "Massive API base URL")
dbutils.widgets.text("rate_limit_delay", "12", "Delay between API calls (seconds)")
dbutils.widgets.text("days_of_history", "30", "Days of price history to fetch")

# Read widget values
WATCHLIST_TABLE_NAME = dbutils.widgets.get("watchlist_table_name")
DETAILS_TABLE_NAME = dbutils.widgets.get("details_table_name")
HISTORY_TABLE_NAME = dbutils.widgets.get("history_table_name")
METRICS_TABLE_NAME = dbutils.widgets.get("metrics_table_name")
MASSIVE_SECRET_SCOPE = dbutils.widgets.get("massive_secret_scope")
MASSIVE_SECRET_KEY = dbutils.widgets.get("massive_secret_key")
MASSIVE_API_BASE_URL = dbutils.widgets.get("massive_api_base_url")
RATE_LIMIT_DELAY = float(dbutils.widgets.get("rate_limit_delay"))
DAYS_OF_HISTORY = int(dbutils.widgets.get("days_of_history"))

print(f"Configuration:")
print(f"  Watchlist source: {WATCHLIST_TABLE_NAME}")
print(f"  Details destination: {DETAILS_TABLE_NAME}")
print(f"  History destination: {HISTORY_TABLE_NAME}")
print(f"  Metrics destination: {METRICS_TABLE_NAME}")
print(f"  Rate limit delay: {RATE_LIMIT_DELAY}s between API calls")
print(f"  Fetching last {DAYS_OF_HISTORY} days of price history")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Resolve the Lakebase connection URL
# MAGIC
# MAGIC Same secret, same decoding scheme as the news notebook: a single base64-encoded Postgres URL stored in a Databricks secret scope.

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

# Extract connection details
db_host = parsed.hostname
db_port = parsed.port or 5432
db_name = parsed.path.lstrip('/')
db_user = parsed.username
db_password = parsed.password

print(f"Connection details:")
print(f"  Host: {db_host}:{db_port}")
print(f"  Database: {db_name}")
print(f"  User: {db_user}")
print(f"  Using raw credentials from secret")

# COMMAND ----------

# DBTITLE 1,Test Lakebase connection
import psycopg2

print(f"Testing connection to {db_host}:{db_port}/{db_name}")
print(f"Using authentication as user: {db_user}\n")

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
    print(f"✅ Connected successfully!")
    print(f"   Found {count} watchlist entries")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")
    raise

# COMMAND ----------

# MAGIC %md
# MAGIC ## Fetch data from Massive for watchlisted tickers
# MAGIC
# MAGIC This step:
# MAGIC 1. Queries the `watchlist` table to get all tracked symbols
# MAGIC 2. For each ticker, fetches from Massive API:
# MAGIC    - Company details from `/v3/reference/tickers/{symbol}`
# MAGIC    - Last 30 days price history from `/v2/aggs/ticker/{symbol}/range/1/day/{from}/{to}`
# MAGIC    - Current snapshot/metrics from `/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}`
# MAGIC 3. Includes rate limiting (12s delay = ~5 req/min) to stay within free tier quota

# COMMAND ----------

# DBTITLE 1,Fetch watchlist and data from Massive API
import base64 as _b64
import time
from datetime import datetime, timedelta
import requests
import psycopg2


def get_massive_api_key() -> str:
    """Retrieve Massive API key from Databricks secrets"""
    secret = w.secrets.get_secret(scope=MASSIVE_SECRET_SCOPE, key=MASSIVE_SECRET_KEY)
    return _b64.b64decode(secret.value).decode("utf-8")


def get_watchlist_tickers() -> list[str]:
    """Get distinct ticker symbols from watchlist table"""
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


def fetch_ticker_details(symbol: str, api_key: str) -> dict:
    """Fetch company details from Massive API"""
    url = f"{MASSIVE_API_BASE_URL}/v3/reference/tickers/{symbol}"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("status") == "OK" and "results" in data:
            result = data["results"]
            return {
                "symbol": symbol,
                "name": result.get("name"),
                "description": result.get("description"),
                "market": result.get("market"),
                "locale": result.get("locale"),
                "primary_exchange": result.get("primary_exchange"),
                "type": result.get("type"),
                "active": result.get("active", True),
                "currency_name": result.get("currency_name"),
                "market_cap": result.get("market_cap"),
                "homepage_url": result.get("homepage_url"),
                "total_employees": result.get("total_employees"),
                "list_date": result.get("list_date"),
                "sic_code": result.get("sic_code"),
                "sic_description": result.get("sic_description"),
                "logo_url": result.get("branding", {}).get("logo_url"),
                "icon_url": result.get("branding", {}).get("icon_url")
            }
    except Exception as e:
        print(f"  ⚠️  Failed to fetch details for {symbol}: {e}")
        return None


def fetch_price_history(symbol: str, api_key: str, days: int = 30) -> list[dict]:
    """Fetch historical OHLCV data from Massive API
    
    Returns: List of daily price bars (OHLCV data)
    Note: Massive API may return status='DELAYED' for free tier data
    """
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    url = f"{MASSIVE_API_BASE_URL}/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        # Accept both "OK" and "DELAYED" status (free tier returns DELAYED)
        if "results" in data and data.get("results"):
            history = []
            for bar in data["results"]:
                history.append({
                    "symbol": symbol,
                    "date": datetime.fromtimestamp(bar["t"] / 1000).strftime("%Y-%m-%d"),
                    "open": bar.get("o"),
                    "high": bar.get("h"),
                    "low": bar.get("l"),
                    "close": bar.get("c"),
                    "volume": bar.get("v"),
                    "vwap": bar.get("vw"),
                    "transactions": bar.get("n"),
                    "timestamp_ms": bar.get("t")
                })
            return history
        else:
            print(f"  ⚠️  No results in response for {symbol} (status: {data.get('status')})")  
            return []
    except Exception as e:
        print(f"  ❌ Failed to fetch price history for {symbol}: {e}")
        return []


def fetch_ticker_metrics(symbol: str, api_key: str) -> dict:
    """Fetch latest price data from Massive API (previous day's aggregate)"""
    url = f"{MASSIVE_API_BASE_URL}/v2/aggs/ticker/{symbol}/prev"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("status") == "OK" and "results" in data and len(data["results"]) > 0:
            result = data["results"][0]
            
            last_price = result.get("c")
            prev_close = result.get("c")  # This IS the previous close
            day_open = result.get("o")
            
            # Calculate change (will need historical data for accurate prev_close)
            price_change = None
            price_change_pct = None
            
            return {
                "symbol": symbol,
                "last_price": last_price,
                "prev_close": prev_close,
                "price_change": price_change,
                "price_change_pct": price_change_pct,
                "day_open": day_open,
                "day_high": result.get("h"),
                "day_low": result.get("l"),
                "volume": result.get("v"),
                "market_cap": None  # Not available in this endpoint
            }
    except Exception as e:
        print(f"  ⚠️  Failed to fetch metrics for {symbol}: {e}")
        return None


# Main execution
print("Fetching watchlist tickers...")
tickers = get_watchlist_tickers()
print(f"Found {len(tickers)} tickers in watchlist: {', '.join(tickers)}\n")

if not tickers:
    print("⚠️  No tickers in watchlist. Nothing to fetch.")
    dbutils.notebook.exit("No tickers to process")

api_key = get_massive_api_key()

all_details = []
all_history = []
all_metrics = []

for i, symbol in enumerate(tickers, 1):
    print(f"[{i}/{len(tickers)}] Processing {symbol}...")
    
    # Fetch ticker details
    details = fetch_ticker_details(symbol, api_key)
    if details:
        all_details.append(details)
        print(f"  ✅ Fetched details: {details.get('name')}")
    
    time.sleep(RATE_LIMIT_DELAY)  # Rate limit
    
    # Fetch price history
    history = fetch_price_history(symbol, api_key, DAYS_OF_HISTORY)
    if history:
        all_history.extend(history)
        print(f"  ✅ Fetched {len(history)} days of price history")
    
    time.sleep(RATE_LIMIT_DELAY)  # Rate limit
    
    # Fetch current metrics
    metrics = fetch_ticker_metrics(symbol, api_key)
    if metrics:
        all_metrics.append(metrics)
        print(f"  ✅ Fetched current metrics: ${metrics.get('last_price')}")
    
    # Rate limit before next ticker (except last one)
    if i < len(tickers):
        time.sleep(RATE_LIMIT_DELAY)
    print()

print(f"\n📊 Collection Summary:")
print(f"  Details: {len(all_details)} records")
print(f"  Price history: {len(all_history)} records")
print(f"  Metrics: {len(all_metrics)} records")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Upsert ticker details to Lakebase
# MAGIC
# MAGIC Insert or update company information in the `ticker_details` table.

# COMMAND ----------

# DBTITLE 1,Upsert ticker details using psycopg2
import psycopg2
from datetime import datetime

if len(all_details) > 0:
    print(f"Upserting {len(all_details)} ticker details into {DETAILS_TABLE_NAME}...")
    
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
        
        # Prepare data tuples
        insert_data = [
            (
                row['symbol'],
                row.get('name'),
                row.get('description'),
                row.get('market'),
                row.get('locale'),
                row.get('primary_exchange'),
                row.get('type'),
                row.get('active', True),
                row.get('currency_name'),
                row.get('market_cap'),
                row.get('homepage_url'),
                row.get('total_employees'),
                row.get('list_date'),
                row.get('sic_code'),
                row.get('sic_description'),
                row.get('logo_url'),
                row.get('icon_url'),
                datetime.now()
            )
            for row in all_details
        ]
        
        # Upsert with ON CONFLICT DO UPDATE
        upsert_sql = f"""
            INSERT INTO {DETAILS_TABLE_NAME} (
                symbol, name, description, market, locale, primary_exchange, type, active,
                currency_name, market_cap, homepage_url, total_employees, list_date,
                sic_code, sic_description, logo_url, icon_url, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                market = EXCLUDED.market,
                locale = EXCLUDED.locale,
                primary_exchange = EXCLUDED.primary_exchange,
                type = EXCLUDED.type,
                active = EXCLUDED.active,
                currency_name = EXCLUDED.currency_name,
                market_cap = EXCLUDED.market_cap,
                homepage_url = EXCLUDED.homepage_url,
                total_employees = EXCLUDED.total_employees,
                list_date = EXCLUDED.list_date,
                sic_code = EXCLUDED.sic_code,
                sic_description = EXCLUDED.sic_description,
                logo_url = EXCLUDED.logo_url,
                icon_url = EXCLUDED.icon_url,
                updated_at = EXCLUDED.updated_at
        """
        
        cursor.executemany(upsert_sql, insert_data)
        conn.commit()
        
        print(f"✅ Successfully upserted {cursor.rowcount} ticker details")
        
    finally:
        cursor.close()
        conn.close()
else:
    print("No ticker details to upsert.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Upsert price history to Lakebase
# MAGIC
# MAGIC Insert or update historical OHLCV data in the `price_history` table.

# COMMAND ----------

# DBTITLE 1,Upsert price history using psycopg2
import psycopg2
from datetime import datetime

if len(all_history) > 0:
    print(f"Upserting {len(all_history)} price history records into {HISTORY_TABLE_NAME}...")
    
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
        
        # Prepare data tuples
        insert_data = [
            (
                row['symbol'],
                row['date'],
                row.get('open'),
                row.get('high'),
                row.get('low'),
                row.get('close'),
                row.get('volume'),
                row.get('vwap'),
                row.get('transactions'),
                row.get('timestamp_ms'),
                datetime.now()
            )
            for row in all_history
        ]
        
        # Upsert with ON CONFLICT DO UPDATE
        upsert_sql = f"""
            INSERT INTO {HISTORY_TABLE_NAME} (
                symbol, date, open, high, low, close, volume, vwap, transactions, timestamp_ms, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                vwap = EXCLUDED.vwap,
                transactions = EXCLUDED.transactions,
                timestamp_ms = EXCLUDED.timestamp_ms,
                updated_at = EXCLUDED.updated_at
        """
        
        cursor.executemany(upsert_sql, insert_data)
        conn.commit()
        
        print(f"✅ Successfully upserted {cursor.rowcount} price history records")
        
    finally:
        cursor.close()
        conn.close()
else:
    print("No price history to upsert.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Upsert ticker metrics to Lakebase
# MAGIC
# MAGIC Insert or update current market metrics in the `ticker_metrics` table.

# COMMAND ----------

# DBTITLE 1,Upsert ticker metrics using psycopg2
import psycopg2
from datetime import datetime

if len(all_metrics) > 0:
    print(f"Upserting {len(all_metrics)} ticker metrics into {METRICS_TABLE_NAME}...")
    
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
        
        # Prepare data tuples
        insert_data = [
            (
                row['symbol'],
                row.get('last_price'),
                row.get('prev_close'),
                row.get('price_change'),
                row.get('price_change_pct'),
                row.get('day_open'),
                row.get('day_high'),
                row.get('day_low'),
                row.get('volume'),
                row.get('market_cap'),
                datetime.now()
            )
            for row in all_metrics
        ]
        
        # Upsert with ON CONFLICT DO UPDATE
        upsert_sql = f"""
            INSERT INTO {METRICS_TABLE_NAME} (
                symbol, last_price, prev_close, price_change, price_change_pct,
                day_open, day_high, day_low, volume, market_cap, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                last_price = EXCLUDED.last_price,
                prev_close = EXCLUDED.prev_close,
                price_change = EXCLUDED.price_change,
                price_change_pct = EXCLUDED.price_change_pct,
                day_open = EXCLUDED.day_open,
                day_high = EXCLUDED.day_high,
                day_low = EXCLUDED.day_low,
                volume = EXCLUDED.volume,
                market_cap = EXCLUDED.market_cap,
                updated_at = EXCLUDED.updated_at
        """
        
        cursor.executemany(upsert_sql, insert_data)
        conn.commit()
        
        print(f"✅ Successfully upserted {cursor.rowcount} ticker metrics")
        
    finally:
        cursor.close()
        conn.close()
else:
    print("No ticker metrics to upsert.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Ingestion Complete
# MAGIC
# MAGIC All watchlisted tickers have been processed:
# MAGIC - **Ticker Details** → `ticker_details` table
# MAGIC - **Price History** (last 30 days) → `price_history` table  
# MAGIC - **Current Metrics** → `ticker_metrics` table
# MAGIC
# MAGIC You can now query this data from your Flask app or schedule this notebook to run periodically (e.g., daily) to keep the data fresh.

# COMMAND ----------


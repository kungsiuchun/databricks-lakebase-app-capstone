"""
Databricks App boilerplate:
- Serves a small Flask API
- Reads/writes to Lakebase (Databricks-managed Postgres) via lakebase.py
- Pulls data from the Massive API via massive_client.py and syncs it into Lakebase

Security Features:
- API Key Authentication: Admin/sync endpoints require API key in X-API-Key header
- Rate Limiting: 5 requests per minute on protected endpoints

Protected Endpoints (require API key):
- /sync, /news/sync, /records - Admin data sync operations

Public Endpoints (no API key needed):
- /watchlist, /ticker/* - Used by the frontend UI

Configuration:
- Set API_KEYS environment variable (comma-separated for multiple keys)
  Example: API_KEYS="admin-key-1,admin-key-2"
  Default: "default-dev-key-change-in-production" (CHANGE IN PRODUCTION!)

Run locally:
    python app.py

Deploy as a Databricks App using app.yaml.
"""

import logging
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps

import requests
from databricks.sdk import WorkspaceClient
from flask import Flask, jsonify, render_template, request

import lakebase
from massive_client import MassiveClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("massive-app")

app = Flask(__name__)
_w = WorkspaceClient()

# ============================================================================
# API Key & Rate Limiting Configuration
# ============================================================================

# API key(s) for authentication (comma-separated for multiple keys)
API_KEYS = set(
    key.strip() 
    for key in os.environ.get("API_KEYS", "default-dev-key-change-in-production").split(",") 
    if key.strip()
)

# Rate limiting: 5 requests per minute
RATE_LIMIT = 5
RATE_LIMIT_WINDOW = 60  # seconds

# In-memory rate limiter storage (use Redis in production for multi-instance deployments)
_rate_limit_store = defaultdict(list)


def require_api_key(f):
    """
    Decorator to require a valid API key in the X-API-Key header.
    
    Usage:
        @app.route("/protected")
        @require_api_key
        def protected_endpoint():
            return jsonify({"data": "secret"})
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        
        if not api_key:
            return jsonify({
                "error": "Missing API key",
                "message": "Please provide an API key in the X-API-Key header"
            }), 401
        
        if api_key not in API_KEYS:
            return jsonify({
                "error": "Invalid API key",
                "message": "The provided API key is not valid"
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated_function


def rate_limit(f):
    """
    Decorator to enforce rate limiting (5 requests per minute).
    Tracks by API key if present, otherwise by IP address.
    
    Usage:
        @app.route("/limited")
        @rate_limit
        @require_api_key
        def limited_endpoint():
            return jsonify({"data": "rate limited"})
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Identify the client by API key (if present) or IP address
        api_key = request.headers.get("X-API-Key")
        client_id = api_key if api_key else request.remote_addr
        
        current_time = time.time()
        
        # Clean up old entries outside the rate limit window
        _rate_limit_store[client_id] = [
            timestamp 
            for timestamp in _rate_limit_store[client_id] 
            if current_time - timestamp < RATE_LIMIT_WINDOW
        ]
        
        # Check if rate limit is exceeded
        if len(_rate_limit_store[client_id]) >= RATE_LIMIT:
            oldest_request = _rate_limit_store[client_id][0]
            retry_after = int(RATE_LIMIT_WINDOW - (current_time - oldest_request))
            
            return jsonify({
                "error": "Rate limit exceeded",
                "message": f"You have exceeded the rate limit of {RATE_LIMIT} requests per {RATE_LIMIT_WINDOW} seconds",
                "retry_after": retry_after
            }), 429
        
        # Record this request
        _rate_limit_store[client_id].append(current_time)
        
        return f(*args, **kwargs)
    
    return decorated_function


TABLE_NAME = os.environ.get("MASSIVE_TABLE_NAME", "massive_records")
WATCHLIST_TABLE_NAME = os.environ.get("WATCHLIST_TABLE_NAME", "watchlist")
NEWS_TABLE_NAME = os.environ.get("NEWS_TABLE_NAME", "ticker_news_documents")
TICKER_DETAILS_TABLE = os.environ.get("TICKER_DETAILS_TABLE", "ticker_details")
PRICE_HISTORY_TABLE = os.environ.get("PRICE_HISTORY_TABLE", "price_history")
TICKER_METRICS_TABLE = os.environ.get("TICKER_METRICS_TABLE", "ticker_metrics")

# Benchmark ticker for comparison (S&P 500 ETF)
BENCHMARK_SYMBOL = os.environ.get("BENCHMARK_SYMBOL", "SPY")

# Tickers to fetch news for by default (comma-separated), e.g. "AAPL,MSFT,GOOGL"
DEFAULT_NEWS_TICKERS = [
    t.strip().upper()
    for t in os.environ.get("NEWS_TICKERS", "AAPL,MSFT,GOOGL,AMZN,TSLA").split(",")
    if t.strip()
]

# Basic stock ticker shape check: 1-10 uppercase letters, with an optional
# ".X" or ".XX" share-class suffix (e.g. "BRK.B"). This rejects obviously
# malformed input before we even call the Massive API.
_TICKER_RE = re.compile(r"^[A-Z]{1,10}(\.[A-Z]{1,2})?$")


def ensure_table():
    """Create the destination table in Lakebase if it doesn't exist yet."""
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id TEXT PRIMARY KEY,
            payload JSONB NOT NULL,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def ensure_watchlist_table():
    """Create the watchlist table in Lakebase if it doesn't exist yet."""
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {WATCHLIST_TABLE_NAME} (
            symbol TEXT NOT NULL,
            email TEXT NOT NULL,
            latest_price NUMERIC,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (symbol, email)
        )
        """
    )
    # Grant permissions to all users
    try:
        lakebase.run_write(f"GRANT ALL ON TABLE {WATCHLIST_TABLE_NAME} TO PUBLIC")
    except Exception as e:
        logger.warning(f"Could not grant permissions on {WATCHLIST_TABLE_NAME}: {e}")


def ensure_news_table():
    """
    Create the raw ticker-news documents table in Lakebase if it doesn't
    exist yet. This is the RAW document store the Spark notebook
    (notebooks/ingest_ticker_news_embeddings.py) reads from to compute
    vector embeddings into a separate `<NEWS_TABLE_NAME>_embeddings` table.
    """
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {NEWS_TABLE_NAME} (
            id TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            author TEXT,
            article_url TEXT,
            publisher_name TEXT,
            keywords JSONB,
            sentiment TEXT,
            sentiment_reasoning TEXT,
            published_utc TIMESTAMPTZ,
            payload JSONB NOT NULL,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    lakebase.run_write(
        f"CREATE INDEX IF NOT EXISTS idx_{NEWS_TABLE_NAME}_ticker "
        f"ON {NEWS_TABLE_NAME} (ticker)"
    )


def ensure_ticker_details_table():
    """Create the ticker_details table for company profiles."""
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {TICKER_DETAILS_TABLE} (
            symbol VARCHAR(10) PRIMARY KEY,
            name VARCHAR(255),
            description TEXT,
            market VARCHAR(50),
            locale VARCHAR(10),
            primary_exchange VARCHAR(50),
            type VARCHAR(50),
            active BOOLEAN DEFAULT TRUE,
            currency_name VARCHAR(50),
            market_cap BIGINT,
            homepage_url TEXT,
            total_employees INTEGER,
            list_date DATE,
            sic_code VARCHAR(10),
            sic_description VARCHAR(255),
            logo_url TEXT,
            icon_url TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def ensure_price_history_table():
    """Create the price_history table for historical OHLC data."""
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {PRICE_HISTORY_TABLE} (
            symbol VARCHAR(10) NOT NULL,
            date DATE NOT NULL,
            open NUMERIC(12, 4),
            high NUMERIC(12, 4),
            low NUMERIC(12, 4),
            close NUMERIC(12, 4),
            volume BIGINT,
            vwap NUMERIC(12, 4),
            transactions INTEGER,
            timestamp_ms BIGINT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, date)
        )
        """
    )
    lakebase.run_write(
        f"CREATE INDEX IF NOT EXISTS idx_{PRICE_HISTORY_TABLE}_symbol_date "
        f"ON {PRICE_HISTORY_TABLE} (symbol, date DESC)"
    )


def ensure_ticker_metrics_table():
    """Create the ticker_metrics table for current market metrics."""
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {TICKER_METRICS_TABLE} (
            symbol VARCHAR(10) PRIMARY KEY,
            last_price NUMERIC(12, 4),
            prev_close NUMERIC(12, 4),
            price_change NUMERIC(12, 4),
            price_change_pct NUMERIC(8, 4),
            day_open NUMERIC(12, 4),
            day_high NUMERIC(12, 4),
            day_low NUMERIC(12, 4),
            volume BIGINT,
            market_cap BIGINT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def ensure_benchmark_data():
    """
    Ensure benchmark (SPY) data exists for comparison.
    Called on first request to /ticker/<symbol>/compare if SPY data is missing.
    The daily sync job will keep it updated after initial sync.
    """
    try:
        # Check if SPY data already exists
        rows = lakebase.run_query(
            f"SELECT symbol FROM {TICKER_DETAILS_TABLE} WHERE symbol = %s",
            (BENCHMARK_SYMBOL,),
        )
        
        if rows:
            logger.info(f"Benchmark data for {BENCHMARK_SYMBOL} already exists")
            return True
        
        logger.info(f"Syncing benchmark data for {BENCHMARK_SYMBOL} (first time)...")
        client = MassiveClient()
        
        # Sync company details
        details = _sync_ticker_details(client, BENCHMARK_SYMBOL)
        if not details:
            logger.error(f"Failed to sync {BENCHMARK_SYMBOL} details")
            return False
        
        # Sync 1 year of price history for meaningful comparisons
        history_count = _sync_price_history(client, BENCHMARK_SYMBOL, days=365)
        if history_count == 0:
            logger.error(f"Failed to sync {BENCHMARK_SYMBOL} price history")
            return False
        
        # Calculate and store metrics
        _calculate_and_store_metrics(BENCHMARK_SYMBOL)
        
        logger.info(f"Successfully synced {BENCHMARK_SYMBOL} benchmark data ({history_count} records)")
        return True
    
    except Exception as e:
        logger.exception(f"Error ensuring benchmark data: {e}")
        return False


def _sync_ticker_details(client: MassiveClient, symbol: str) -> dict | None:
    """
    Fetch company details from Polygon API and upsert into ticker_details table.
    Returns the details dict or None if fetch failed.
    """
    import json as _json
    
    try:
        details = client.get_ticker_details(symbol)
        if not details:
            logger.warning(f"No details returned for {symbol}")
            return None
        
        # Extract branding info
        branding = details.get("branding", {})
        
        with lakebase.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {TICKER_DETAILS_TABLE} (
                        symbol, name, description, market, locale, primary_exchange,
                        type, active, currency_name, market_cap, homepage_url,
                        total_employees, list_date, sic_code, sic_description, logo_url, icon_url, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (symbol) DO UPDATE
                        SET name = EXCLUDED.name,
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
                    """,
                    (
                        symbol,
                        details.get("name", ""),
                        details.get("description"),
                        details.get("market"),
                        details.get("locale"),
                        details.get("primary_exchange"),
                        details.get("type"),
                        details.get("active", True),
                        details.get("currency_name"),
                        details.get("market_cap"),
                        details.get("homepage_url"),
                        details.get("total_employees"),
                        details.get("list_date"),
                        details.get("sic_code"),
                        details.get("sic_description"),
                        branding.get("logo_url"),
                        branding.get("icon_url"),
                    ),
                )
                conn.commit()
        
        logger.info(f"Synced ticker details for {symbol}")
        return details
    
    except Exception as e:
        logger.exception(f"Failed to sync ticker details for {symbol}: {e}")
        return None


def _sync_price_history(client: MassiveClient, symbol: str, days: int = 90) -> int:
    """
    Fetch historical price data from Polygon API and upsert into price_history table.
    Returns the number of records inserted/updated.
    """
    try:
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        history = client.get_price_history(symbol, from_date, to_date, timespan="day")
        if not history:
            logger.warning(f"No price history returned for {symbol}")
            return 0
        
        count = 0
        with lakebase.get_connection() as conn:
            with conn.cursor() as cur:
                for bar in history:
                    # Convert timestamp from milliseconds to date
                    timestamp_ms = bar.get("t")
                    date = datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d") if timestamp_ms else None
                    
                    if not date:
                        continue
                    
                    cur.execute(
                        f"""
                        INSERT INTO {PRICE_HISTORY_TABLE} (
                            symbol, date, open, high, low, close, volume, vwap,
                            transactions, timestamp_ms, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                        ON CONFLICT (symbol, date) DO UPDATE
                            SET open = EXCLUDED.open,
                                high = EXCLUDED.high,
                                low = EXCLUDED.low,
                                close = EXCLUDED.close,
                                volume = EXCLUDED.volume,
                                vwap = EXCLUDED.vwap,
                                transactions = EXCLUDED.transactions,
                                timestamp_ms = EXCLUDED.timestamp_ms,
                                updated_at = EXCLUDED.updated_at
                        """,
                        (
                            symbol,
                            date,
                            bar.get("o"),  # open
                            bar.get("h"),  # high
                            bar.get("l"),  # low
                            bar.get("c"),  # close
                            bar.get("v"),  # volume
                            bar.get("vw"), # vwap
                            bar.get("n"),  # transactions
                            timestamp_ms,
                        ),
                    )
                    count += 1
                
                conn.commit()
        
        logger.info(f"Synced {count} price history records for {symbol}")
        return count
    
    except Exception as e:
        logger.exception(f"Failed to sync price history for {symbol}: {e}")
        return 0


def _calculate_and_store_metrics(symbol: str):
    """
    Calculate current metrics from latest price data and store in ticker_metrics table.
    """
    try:
        # Get the two most recent price records
        rows = lakebase.run_query(
            f"SELECT date, open, high, low, close, volume, vwap "
            f"FROM {PRICE_HISTORY_TABLE} "
            f"WHERE symbol = %s ORDER BY date DESC LIMIT 2",
            (symbol,),
        )
        
        if not rows:
            logger.warning(f"No price history found for {symbol} to calculate metrics")
            return
        
        latest = rows[0]
        prev = rows[1] if len(rows) > 1 else latest
        
        last_price = latest.get("close")
        prev_close = prev.get("close")
        price_change = (last_price - prev_close) if (last_price and prev_close) else None
        price_change_pct = (price_change / prev_close * 100) if (price_change and prev_close) else None
        
        # Get market cap from ticker_details
        details_rows = lakebase.run_query(
            f"SELECT market_cap FROM {TICKER_DETAILS_TABLE} WHERE symbol = %s",
            (symbol,),
        )
        market_cap = details_rows[0].get("market_cap") if details_rows else None
        
        with lakebase.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {TICKER_METRICS_TABLE} (
                        symbol, last_price, prev_close, price_change, price_change_pct,
                        day_open, day_high, day_low, volume, market_cap, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (symbol) DO UPDATE
                        SET last_price = EXCLUDED.last_price,
                            prev_close = EXCLUDED.prev_close,
                            price_change = EXCLUDED.price_change,
                            price_change_pct = EXCLUDED.price_change_pct,
                            day_open = EXCLUDED.day_open,
                            day_high = EXCLUDED.day_high,
                            day_low = EXCLUDED.day_low,
                            volume = EXCLUDED.volume,
                            market_cap = EXCLUDED.market_cap,
                            updated_at = EXCLUDED.updated_at
                    """,
                    (
                        symbol,
                        last_price,
                        prev_close,
                        price_change,
                        price_change_pct,
                        latest.get("open"),
                        latest.get("high"),
                        latest.get("low"),
                        latest.get("volume"),
                        market_cap,
                    ),
                )
                conn.commit()
        
        logger.info(f"Calculated and stored metrics for {symbol}")
    
    except Exception as e:
        logger.exception(f"Failed to calculate metrics for {symbol}: {e}")


def _current_user_email() -> str:
    """
    Resolve the current user's email so the watchlist can be personalized.

    Databricks Apps inject the logged-in user's identity via the
    X-Forwarded-Email header on every request. Fall back to the Databricks
    SDK's current_user API for local development where that header isn't set.
    """
    header_email = request.headers.get("X-Forwarded-Email")
    if header_email:
        return header_email
    return _w.current_user.me().user_name


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.errorhandler(Exception)
def handle_exception(err):
    """Ensure all unhandled errors return JSON (not an HTML error page),
    so the frontend's resp.json() call never chokes on HTML."""
    logger.exception("Unhandled exception while processing request")
    status_code = getattr(err, "code", 500)
    if not isinstance(status_code, int):
        status_code = 500
    return jsonify({"error": str(err)}), status_code


@app.route("/")
def index():
    """Simple UI to submit a list of stock symbols to sync from Massive."""
    return render_template("index.html")


@app.route("/ticker")
def ticker_detail():
    """Ticker detail page with company profile, charts, and news."""
    return render_template("ticker_detail.html")


@app.route("/records")
@rate_limit
@require_api_key
def list_records():
    """Read records already synced into Lakebase."""
    limit = int(request.args.get("limit", 100))
    rows = lakebase.run_query(
        f"SELECT id, payload, synced_at FROM {TABLE_NAME} ORDER BY synced_at DESC LIMIT %s",
        (limit,),
    )
    return jsonify(rows)


@app.route("/sync", methods=["POST"])
@rate_limit
@require_api_key
def sync_from_massive():
    """
    Pull data from the Massive API (paginated, potentially huge dataset) and
    upsert it into Lakebase in batches.
    """
    ensure_table()
    client = MassiveClient()

    path = request.json.get("path", "/records") if request.is_json else "/records"
    batch_size = int(request.args.get("batch_size", 500))

    batch = []
    total = 0
    for item in client.paginated_get(path):
        batch.append(item)
        if len(batch) >= batch_size:
            total += _upsert_batch(batch)
            batch = []

    if batch:
        total += _upsert_batch(batch)

    return jsonify({"synced": total})


@app.route("/news/sync", methods=["POST"])
@rate_limit
@require_api_key
def sync_news_from_massive():
    """
    Pull recent news articles for a set of tickers from Massive (ONE API
    call per ticker, via MassiveClient.get_news) and upsert them into the
    ticker_news_documents table in Lakebase.

    Body (optional JSON): {"tickers": ["AAPL", "MSFT"], "limit": 50}
    Defaults to DEFAULT_NEWS_TICKERS when no tickers are supplied.
    """
    ensure_news_table()
    client = MassiveClient()

    body = request.json if request.is_json else {}
    tickers = body.get("tickers") or DEFAULT_NEWS_TICKERS
    tickers = [t.strip().upper() for t in tickers if isinstance(t, str) and t.strip()]
    limit = int(body.get("limit", 50))

    total = 0
    for ticker in tickers:
        if not _TICKER_RE.match(ticker):
            continue
        articles = client.get_news(ticker, limit=limit)
        total += _upsert_news_batch(ticker, articles)

    return jsonify({"synced": total, "tickers": tickers})


@app.route("/watchlist", methods=["GET"])
def get_watchlist():
    """Return the current user's watchlist symbols, with their last known price."""
    ensure_watchlist_table()
    email = _current_user_email()
    rows = lakebase.run_query(
        f"SELECT symbol, email, latest_price, updated_at FROM {WATCHLIST_TABLE_NAME} "
        f"WHERE email = %s ORDER BY symbol ASC",
        (email,),
    )
    return jsonify(rows)


@app.route("/watchlist", methods=["POST"])
def add_to_watchlist():
    """
    Add a ticker to the watchlist with IMMEDIATE data fetch (Hybrid Flow):
    1. Fetch latest price from Polygon API
    2. Fetch company details and store in ticker_details
    3. Fetch last 90 days of price history and store in price_history
    4. Calculate and store current metrics in ticker_metrics
    5. Add to watchlist table
    
    This ensures the user sees charts and company info immediately.
    Daily batch jobs will keep the data updated after initial fetch.
    """
    ensure_watchlist_table()
    ensure_ticker_details_table()
    ensure_price_history_table()
    ensure_ticker_metrics_table()

    if request.is_json:
        symbol = request.json.get("symbol", "")
    else:
        symbol = request.form.get("symbol", "")

    symbol = symbol.strip().upper() if isinstance(symbol, str) else ""

    if not symbol or not _TICKER_RE.match(symbol):
        return jsonify({"error": f"Invalid ticker symbol: {symbol!r}"}), 400

    client = MassiveClient()
    
    # Step 1: Fetch latest price (quick validation that ticker exists)
    try:
        data = client.get_latest_price(symbol)
    except requests.HTTPError:
        return jsonify({"error": f"Unknown ticker symbol: {symbol}"}), 400

    price = _extract_latest_price(data)
    if price is None:
        return jsonify({"error": f"No price data available for ticker: {symbol}"}), 400

    # Step 2: Fetch and store company details (name, logo, description, etc.)
    logger.info(f"Fetching ticker details for {symbol}...")
    details = _sync_ticker_details(client, symbol)
    
    # Step 3: Fetch and store 90 days of price history (for charts)
    logger.info(f"Fetching price history for {symbol}...")
    history_count = _sync_price_history(client, symbol, days=90)
    
    # Step 4: Calculate and store current metrics
    if history_count > 0:
        logger.info(f"Calculating metrics for {symbol}...")
        _calculate_and_store_metrics(symbol)
    
    # Step 5: Add to watchlist
    email = _current_user_email()
    lakebase.run_write(
        f"""
        INSERT INTO {WATCHLIST_TABLE_NAME} (symbol, email, latest_price, updated_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (symbol, email) DO UPDATE
            SET latest_price = EXCLUDED.latest_price,
                updated_at = EXCLUDED.updated_at
        """,
        (symbol, email, price),
    )

    return jsonify({
        "symbol": symbol,
        "email": email,
        "latest_price": price,
        "details_synced": details is not None,
        "history_records": history_count,
        "message": f"Added {symbol} to watchlist with full data sync"
    })


@app.route("/watchlist/<symbol>", methods=["DELETE"])
def delete_from_watchlist(symbol: str):
    """Remove a single symbol from the current user's watchlist."""
    ensure_watchlist_table()

    symbol = symbol.strip().upper() if isinstance(symbol, str) else ""
    if not symbol or not _TICKER_RE.match(symbol):
        return jsonify({"error": f"Invalid ticker symbol: {symbol!r}"}), 400

    email = _current_user_email()
    deleted = lakebase.run_write(
        f"DELETE FROM {WATCHLIST_TABLE_NAME} WHERE symbol = %s AND email = %s",
        (symbol, email),
    )

    if not deleted:
        return jsonify({"error": f"{symbol} is not on your watchlist"}), 404

    return jsonify({"symbol": symbol, "email": email, "deleted": True})


@app.route("/ticker/<symbol>/details", methods=["GET"])
def get_ticker_details(symbol: str):
    """
    Get company profile and details for a ticker.
    
    Flow:
    1. Try to fetch from database (if ticker is in watchlist)
    2. If not found, fetch directly from Polygon API
    3. Return data (API data is NOT saved to database - only saved when added to watchlist)
    
    Returns company name, description, logo, market cap, homepage, etc.
    """
    symbol = symbol.strip().upper() if isinstance(symbol, str) else ""
    if not symbol or not _TICKER_RE.match(symbol):
        return jsonify({"error": f"Invalid ticker symbol: {symbol!r}"}), 400
    
    # Try database first
    rows = lakebase.run_query(
        f"SELECT * FROM {TICKER_DETAILS_TABLE} WHERE symbol = %s",
        (symbol,),
    )
    
    if rows:
        # Found in database - return from DB
        details = dict(rows[0])
        if details.get('logo_url'):
            # Replace direct Polygon URL with our proxy endpoint
            details['logo_url'] = f"/logo/{symbol}"
        return jsonify(details)
    
    # Not in database - fetch from Polygon API
    try:
        client = MassiveClient()
        api_details = client.get_ticker_details(symbol)
        
        if not api_details:
            return jsonify({"error": f"Ticker {symbol} not found in Polygon API"}), 404
        
        # Extract branding info
        branding = api_details.get("branding", {})
        
        # Format response to match database structure
        details = {
            "symbol": symbol,
            "name": api_details.get("name", ""),
            "description": api_details.get("description"),
            "market": api_details.get("market"),
            "locale": api_details.get("locale"),
            "primary_exchange": api_details.get("primary_exchange"),
            "type": api_details.get("type"),
            "active": api_details.get("active", True),
            "currency_name": api_details.get("currency_name"),
            "market_cap": api_details.get("market_cap"),
            "homepage_url": api_details.get("homepage_url"),
            "total_employees": api_details.get("total_employees"),
            "list_date": api_details.get("list_date"),
            "sic_code": api_details.get("sic_code"),
            "sic_description": api_details.get("sic_description"),
            "logo_url": f"/logo/{symbol}" if branding.get("logo_url") else None,
            "icon_url": branding.get("icon_url"),
        }
        
        return jsonify(details)
    
    except Exception as e:
        logger.exception(f"Failed to fetch ticker details for {symbol}: {e}")
        return jsonify({"error": f"Failed to fetch details for {symbol}"}), 500


@app.route("/ticker/<symbol>/history", methods=["GET"])
def get_ticker_history(symbol: str):
    """
    Get historical price data (OHLC) for a ticker.
    
    Flow:
    1. Try to fetch from database (if ticker is in watchlist)
    2. If not found, fetch directly from Polygon API
    3. Return data (API data is NOT saved to database - only saved when added to watchlist)
    
    Query params:
        - days: Number of days of history to return (default: 90, max: 365)
        - limit: Maximum number of records (default: 100, max: 1000)
    
    Returns array of OHLC bars sorted by date descending (most recent first).
    """
    symbol = symbol.strip().upper() if isinstance(symbol, str) else ""
    if not symbol or not _TICKER_RE.match(symbol):
        return jsonify({"error": f"Invalid ticker symbol: {symbol!r}"}), 400
    
    days = min(int(request.args.get("days", 90)), 365)
    limit = min(int(request.args.get("limit", 100)), 1000)
    
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    # Try database first
    rows = lakebase.run_query(
        f"SELECT symbol, date, open, high, low, close, volume, vwap, transactions "
        f"FROM {PRICE_HISTORY_TABLE} "
        f"WHERE symbol = %s AND date >= %s "
        f"ORDER BY date DESC LIMIT %s",
        (symbol, from_date, limit),
    )
    
    if rows:
        # Found in database - return from DB
        return jsonify({
            "symbol": symbol,
            "from_date": from_date,
            "records": len(rows),
            "history": rows
        })
    
    # Not in database - fetch from Polygon API
    try:
        client = MassiveClient()
        to_date = datetime.now().strftime("%Y-%m-%d")
        
        api_history = client.get_price_history(symbol, from_date, to_date, timespan="day")
        
        if not api_history:
            return jsonify({"error": f"No price history available for {symbol}"}), 404
        
        # Format API response to match database structure
        history = []
        for bar in api_history[:limit]:  # Respect limit parameter
            # Convert timestamp from milliseconds to date
            timestamp_ms = bar.get("t")
            date = datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d") if timestamp_ms else None
            
            if date:
                history.append({
                    "symbol": symbol,
                    "date": date,
                    "open": float(bar.get("o")) if bar.get("o") else None,
                    "high": float(bar.get("h")) if bar.get("h") else None,
                    "low": float(bar.get("l")) if bar.get("l") else None,
                    "close": float(bar.get("c")) if bar.get("c") else None,
                    "volume": int(bar.get("v")) if bar.get("v") else None,
                    "vwap": float(bar.get("vw")) if bar.get("vw") else None,
                    "transactions": int(bar.get("n")) if bar.get("n") else None,
                })
        
        # Sort by date descending (most recent first) to match database behavior
        history.sort(key=lambda x: x["date"], reverse=True)
        
        return jsonify({
            "symbol": symbol,
            "from_date": from_date,
            "records": len(history),
            "history": history
        })
    
    except Exception as e:
        logger.exception(f"Failed to fetch price history for {symbol}: {e}")
        return jsonify({"error": f"Failed to fetch price history for {symbol}"}), 500


@app.route("/ticker/<symbol>/metrics", methods=["GET"])
def get_ticker_metrics(symbol: str):
    """
    Get current market metrics for a ticker.
    
    Flow:
    1. Try to fetch from database (if ticker is in watchlist)
    2. If not found, fetch directly from Polygon API
    3. Return data (API data is NOT saved to database)
    
    Returns latest price, % change, volume, market cap, etc.
    """
    symbol = symbol.strip().upper() if isinstance(symbol, str) else ""
    if not symbol or not _TICKER_RE.match(symbol):
        return jsonify({"error": f"Invalid ticker symbol: {symbol!r}"}), 400
    
    # Try database first
    rows = lakebase.run_query(
        f"SELECT * FROM {TICKER_METRICS_TABLE} WHERE symbol = %s",
        (symbol,),
    )
    
    if rows:
        # Found in database - return from DB
        return jsonify(rows[0])
    
    # Not in database - fetch from Polygon API
    try:
        client = MassiveClient()
        api_data = client.get_latest_price(symbol)
        
        if not api_data or not api_data.get("results"):
            # No data available - return null metrics
            return jsonify({
                "symbol": symbol,
                "last_price": None,
                "prev_close": None,
                "price_change": None,
                "price_change_pct": None,
                "day_open": None,
                "day_high": None,
                "day_low": None,
                "volume": None,
                "market_cap": None
            })
        
        results = api_data.get("results", [])
        if isinstance(results, list) and len(results) > 0:
            result = results[0]
        else:
            result = results if isinstance(results, dict) else {}
        
        # Extract metrics from API response
        close = float(result.get("c", 0)) if result.get("c") else None
        prev_close = float(result.get("pc", close or 0)) if result.get("pc") else close
        
        # Calculate change
        if close and prev_close:
            price_change = close - prev_close
            price_change_pct = (price_change / prev_close) * 100
        else:
            price_change = None
            price_change_pct = None
        
        metrics = {
            "symbol": symbol,
            "last_price": close,
            "prev_close": prev_close,
            "price_change": price_change,
            "price_change_pct": price_change_pct,
            "day_open": float(result.get("o", 0)) if result.get("o") else None,
            "day_high": float(result.get("h", 0)) if result.get("h") else None,
            "day_low": float(result.get("l", 0)) if result.get("l") else None,
            "volume": int(result.get("v", 0)) if result.get("v") else None,
            "market_cap": None  # Not available in previous close endpoint
        }
        
        return jsonify(metrics)
    
    except Exception as e:
        logger.exception(f"Failed to fetch metrics for {symbol}: {e}")
        return jsonify({"error": f"Failed to fetch metrics for {symbol}"}), 500


@app.route("/ticker/<symbol>/news", methods=["GET"])
def get_ticker_news(symbol: str):
    """
    Get recent news articles for a ticker from the ticker_news_documents table.
    
    Query params:
        - limit: Maximum number of articles to return (default: 20, max: 50)
    
    Returns array of news articles sorted by published_utc descending (most recent first).
    """
    symbol = symbol.strip().upper() if isinstance(symbol, str) else ""
    if not symbol or not _TICKER_RE.match(symbol):
        return jsonify({"error": f"Invalid ticker symbol: {symbol!r}"}), 400
    
    # Get limit from query params
    limit = request.args.get('limit', 20, type=int)
    limit = min(max(1, limit), 50)  # Clamp between 1 and 50
    
    try:
        # Try database first
        rows = lakebase.run_query(
            f"""
            SELECT 
                id,
                ticker,
                title,
                description,
                author,
                article_url,
                publisher_name,
                sentiment,
                sentiment_reasoning,
                published_utc,
                synced_at,
                payload
            FROM ticker_news_documents
            WHERE ticker = %s
            ORDER BY published_utc DESC
            LIMIT %s
            """,
            (symbol, limit),
        )
        
        if rows:
            # Found in database - return from DB
            articles = [dict(row) for row in rows]
            
            # Format timestamps as ISO strings for JSON serialization
            for article in articles:
                if article.get('published_utc'):
                    article['published_utc'] = article['published_utc'].isoformat()
                if article.get('synced_at'):
                    article['synced_at'] = article['synced_at'].isoformat()
                
                # Extract image_url and publisher details from payload
                if article.get('payload'):
                    payload = article['payload']
                    article['image_url'] = payload.get('image_url')
                    article['publisher'] = payload.get('publisher', {})
            
            return jsonify(articles)
        
        # Not in database - fetch from Polygon API (no save)
        logger.info(f"News not in DB for {symbol}, fetching from Polygon API...")
        client = MassiveClient()
        api_articles = client.get_news(symbol, limit=limit)
        
        if not api_articles:
            # No news available - return empty array
            return jsonify([])
        
        # Format API response for frontend
        formatted_articles = []
        for article in api_articles:
            # Extract sentiment from insights
            sentiment = None
            sentiment_reasoning = None
            if article.get('insights'):
                for insight in article['insights']:
                    if insight.get('ticker') == symbol:
                        sentiment = insight.get('sentiment')
                        sentiment_reasoning = insight.get('sentiment_reasoning')
                        break
            
            formatted_article = {
                'id': article.get('id'),
                'ticker': symbol,
                'title': article.get('title'),
                'description': article.get('description'),
                'author': article.get('author'),
                'article_url': article.get('article_url'),
                'publisher_name': article.get('publisher', {}).get('name'),
                'publisher': article.get('publisher', {}),
                'image_url': article.get('image_url'),
                'sentiment': sentiment,
                'sentiment_reasoning': sentiment_reasoning,
                'published_utc': article.get('published_utc'),
            }
            formatted_articles.append(formatted_article)
        
        return jsonify(formatted_articles)
    
    except Exception as e:
        logger.exception(f"Failed to fetch news for {symbol}: {e}")
        return jsonify({"error": f"Failed to fetch news for {symbol}"}), 500


@app.route("/ticker/<symbol>/compare", methods=["GET"])
def compare_to_benchmark(symbol: str):
    """
    Compare a ticker's performance against S&P 500 benchmark (SPY).
    Returns normalized returns for both ticker and benchmark over the specified period.
    
    Query params:
        - days: Lookback period in days (default: 90, max: 365)
        - benchmark: Override benchmark symbol (default: SPY)
    
    Returns:
        - Normalized returns (percentage change from start) for both ticker and benchmark
        - Alpha (ticker return - benchmark return)
        - Performance summary
    
    Example:
        GET /ticker/AAPL/compare?days=90
        Returns AAPL vs SPY performance over last 90 days
    """
    # Ensure required tables exist
    ensure_ticker_details_table()
    ensure_price_history_table()
    ensure_ticker_metrics_table()
    
    symbol = symbol.strip().upper() if isinstance(symbol, str) else ""
    if not symbol or not _TICKER_RE.match(symbol):
        return jsonify({"error": f"Invalid ticker symbol: {symbol!r}"}), 400
    
    days = min(int(request.args.get("days", 90)), 365)
    benchmark = request.args.get("benchmark", BENCHMARK_SYMBOL).strip().upper()
    
    # Ensure benchmark data exists (auto-sync if missing)
    if benchmark == BENCHMARK_SYMBOL:
        ensure_benchmark_data()
    
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    # Get ticker price history
    ticker_rows = lakebase.run_query(
        f"SELECT date, close FROM {PRICE_HISTORY_TABLE} "
        f"WHERE symbol = %s AND date >= %s ORDER BY date ASC",
        (symbol, from_date),
    )
    
    # Get benchmark price history
    benchmark_rows = lakebase.run_query(
        f"SELECT date, close FROM {PRICE_HISTORY_TABLE} "
        f"WHERE symbol = %s AND date >= %s ORDER BY date ASC",
        (benchmark, from_date),
    )
    
    if not ticker_rows:
        return jsonify({
            "error": f"No price history found for {symbol}. Add it to your watchlist first."
        }), 404
    
    if not benchmark_rows:
        return jsonify({
            "error": f"No benchmark data found for {benchmark}. The daily sync job should add it automatically.",
            "hint": f"Manually add {benchmark} to watchlist or run daily_ticker_sync.py"
        }), 404
    
    # Calculate normalized returns (percentage change from start)
    def normalize_returns(prices):
        """Convert absolute prices to percentage returns from the starting price."""
        if not prices:
            return []
        base = prices[0]["close"]
        if not base or base == 0:
            return []
        return [
            {
                "date": p["date"].strftime("%Y-%m-%d") if hasattr(p["date"], "strftime") else str(p["date"]),
                "close": float(p["close"]) if p["close"] else 0,
                "return_pct": round(((float(p["close"]) - base) / base) * 100, 2) if p["close"] else 0
            }
            for p in prices
        ]
    
    ticker_normalized = normalize_returns(ticker_rows)
    benchmark_normalized = normalize_returns(benchmark_rows)
    
    if not ticker_normalized or not benchmark_normalized:
        return jsonify({"error": "Unable to calculate returns. Check price data."}), 500
    
    # Calculate total returns and alpha
    ticker_total_return = ticker_normalized[-1]["return_pct"]
    benchmark_total_return = benchmark_normalized[-1]["return_pct"]
    alpha = ticker_total_return - benchmark_total_return
    
    # Calculate volatility (standard deviation of daily returns)
    def calculate_volatility(normalized_data):
        """Calculate annualized volatility from daily returns."""
        if len(normalized_data) < 2:
            return None
        daily_returns = [
            normalized_data[i]["return_pct"] - normalized_data[i-1]["return_pct"]
            for i in range(1, len(normalized_data))
        ]
        if not daily_returns:
            return None
        import math
        mean_return = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean_return) ** 2 for r in daily_returns) / len(daily_returns)
        daily_vol = math.sqrt(variance)
        # Annualize: daily vol * sqrt(252 trading days)
        return round(daily_vol * math.sqrt(252), 2)
    
    ticker_volatility = calculate_volatility(ticker_normalized)
    benchmark_volatility = calculate_volatility(benchmark_normalized)
    
    # Calculate Sharpe ratio (simplified: return / volatility, assuming 0% risk-free rate)
    ticker_sharpe = round(ticker_total_return / ticker_volatility, 2) if ticker_volatility and ticker_volatility > 0 else None
    benchmark_sharpe = round(benchmark_total_return / benchmark_volatility, 2) if benchmark_volatility and benchmark_volatility > 0 else None
    
    return jsonify({
        "symbol": symbol,
        "benchmark": benchmark,
        "period_days": days,
        "from_date": from_date,
        "to_date": datetime.now().strftime("%Y-%m-%d"),
        "ticker_data": ticker_normalized,
        "benchmark_data": benchmark_normalized,
        "summary": {
            "ticker_return_pct": round(ticker_total_return, 2),
            "benchmark_return_pct": round(benchmark_total_return, 2),
            "alpha": round(alpha, 2),
            "ticker_volatility": ticker_volatility,
            "benchmark_volatility": benchmark_volatility,
            "ticker_sharpe_ratio": ticker_sharpe,
            "benchmark_sharpe_ratio": benchmark_sharpe,
            "outperformance": alpha > 0,
            "message": f"{symbol} {'outperformed' if alpha > 0 else 'underperformed'} {benchmark} by {abs(alpha):.2f}% over {days} days"
        }
    })


@app.route("/logo/<symbol>")
def get_logo_proxy(symbol: str):
    """
    Proxy company logo through backend to inject API key.
    
    Flow:
    1. Try to get logo URL from database
    2. If not found, fetch from Polygon API
    3. Fetch the logo with API key and serve to browser
    
    Polygon logo URLs require API key authentication, which can't be done
    from frontend <img> tags. This endpoint fetches the logo server-side
    with the API key and serves it directly to the browser.
    
    Returns the logo image with proper content-type, or 404 if not found.
    """
    from flask import Response, abort, redirect
    
    try:
        symbol = symbol.upper().strip()
        logo_url = None
        
        # Try database first
        rows = lakebase.run_query(
            f"SELECT logo_url FROM {TICKER_DETAILS_TABLE} WHERE symbol = %s",
            (symbol,),
        )
        
        if rows and rows[0].get("logo_url"):
            logo_url = rows[0]["logo_url"]
            logger.info(f"Found logo URL in database for {symbol}: {logo_url}")
        
        # Not in database - fetch from API
        if not logo_url:
            client = MassiveClient()
            api_details = client.get_ticker_details(symbol)
            
            if api_details and api_details.get("branding", {}).get("logo_url"):
                logo_url = api_details["branding"]["logo_url"]
            else:
                # No logo available
                abort(404)
        
        # Fetch logo with API key
        if 'api.polygon.io' in logo_url or 'api.massive.com' in logo_url:
            # Get API key from the helper function
            from massive_client import _get_api_key
            api_key = _get_api_key()
            
            # Add API key to request
            params = {'apiKey': api_key}
            response = requests.get(logo_url, params=params, timeout=10)
            
            if response.status_code == 200:
                # Return image with correct content type
                return Response(
                    response.content,
                    content_type=response.headers.get('content-type', 'image/svg+xml')
                )
            else:
                logger.warning(f"Failed to fetch logo for {symbol}: {response.status_code}")
                abort(response.status_code)
        else:
            # External URL (not Polygon), redirect directly
            return redirect(logo_url)
    
    except Exception as e:
        logger.exception(f"Error proxying logo for {symbol}: {e}")
        abort(500)



def _extract_latest_price(data: dict) -> float | None:
    """Pull the trade price out of the Massive 'previous close' response shape.

    The /v2/aggs/ticker/{symbol}/prev endpoint returns "results" as a LIST
    containing a single aggregate bar (not a dict), e.g.:
        {"status": "OK", "resultsCount": 1, "results": [{"c": 148.845, ...}]}
    Previously this code treated "results" as a dict, so isinstance(results, dict)
    was always False for this endpoint's real shape and the price silently
    resolved to None. Unwrap the list here, and check "status"/"resultsCount"
    so invalid tickers (empty results) are detected instead of "succeeding"
    with a null price.

    Adjust the key lookup here if the real Massive API returns a different
    field name for the traded/close price.
    """
    if not isinstance(data, dict):
        return None
    if data.get("status") not in (None, "OK") or data.get("resultsCount") == 0:
        return None
    results = data.get("results", data)
    if isinstance(results, list):
        results = results[0] if results else None
    if isinstance(results, dict):
        for key in ("c", "p", "price", "last_price", "vw"):
            if key in results:
                return results[key]
    return None


def _upsert_batch(items: list[dict]) -> int:
    """Upsert a batch of Massive API items into Lakebase, one statement per row.

    For very large batches, consider psycopg2.extras.execute_values for
    higher throughput instead of per-row execute calls.
    """
    import json as _json

    count = 0
    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            for item in items:
                cur.execute(
                    f"""
                    INSERT INTO {TABLE_NAME} (id, payload, synced_at)
                    VALUES (%s, %s, now())
                    ON CONFLICT (id) DO UPDATE
                        SET payload = EXCLUDED.payload,
                            synced_at = EXCLUDED.synced_at
                    """,
                    (str(item.get("id")), _json.dumps(item)),
                )
                count += 1
            conn.commit()
    return count


def _upsert_news_batch(ticker: str, articles: list[dict]) -> int:
    """Upsert news articles for a single ticker into the news documents table.

    Flattens the top-level "insights" sentiment entry that matches this
    ticker (if present) into its own columns so the Spark notebook can read
    plain text columns instead of parsing JSONB for the common case.
    """
    import json as _json

    count = 0
    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            for article in articles:
                sentiment = None
                sentiment_reasoning = None
                for insight in article.get("insights", []) or []:
                    if insight.get("ticker") == ticker:
                        sentiment = insight.get("sentiment")
                        sentiment_reasoning = insight.get("sentiment_reasoning")
                        break

                publisher = article.get("publisher") or {}
                cur.execute(
                    f"""
                    INSERT INTO {NEWS_TABLE_NAME} (
                        id, ticker, title, description, author, article_url,
                        publisher_name, keywords, sentiment, sentiment_reasoning,
                        published_utc, payload, synced_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (id) DO UPDATE
                        SET ticker = EXCLUDED.ticker,
                            title = EXCLUDED.title,
                            description = EXCLUDED.description,
                            author = EXCLUDED.author,
                            article_url = EXCLUDED.article_url,
                            publisher_name = EXCLUDED.publisher_name,
                            keywords = EXCLUDED.keywords,
                            sentiment = EXCLUDED.sentiment,
                            sentiment_reasoning = EXCLUDED.sentiment_reasoning,
                            published_utc = EXCLUDED.published_utc,
                            payload = EXCLUDED.payload,
                            synced_at = EXCLUDED.synced_at
                    """,
                    (
                        str(article.get("id")),
                        ticker,
                        article.get("title", ""),
                        article.get("description"),
                        article.get("author"),
                        article.get("article_url"),
                        publisher.get("name"),
                        _json.dumps(article.get("keywords", [])),
                        sentiment,
                        sentiment_reasoning,
                        article.get("published_utc"),
                        _json.dumps(article),
                    ),
                )
                count += 1
            conn.commit()
    return count




if __name__ == '__main__':
    # Initialize database tables before starting the app
    host = os.getenv('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_RUN_PORT', 8000))
    logger.info(f"Starting Flask app on http://{host}:{port}")
    app.run(debug=True, host=host, port=port)
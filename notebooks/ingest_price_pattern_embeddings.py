# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # Ingest Price Pattern Embeddings (Lakebase)
# MAGIC
# MAGIC This notebook creates **three types of embeddings** following the news embeddings pattern:
# MAGIC
# MAGIC ## 1. Company Description Embeddings
# MAGIC - **Source**: `ticker_details.description` (direct text)
# MAGIC - **Use case**: Semantic search for companies by business description
# MAGIC - **Example**: "Find companies working on AI chips"
# MAGIC
# MAGIC ## 2. Technical State Embeddings  
# MAGIC - **Source**: `technical_indicators` table (SMA, EMA, MACD, RSI)
# MAGIC - **Text generation**: Technical narrative from indicator values
# MAGIC - **Use case**: Find tickers with similar technical patterns
# MAGIC - **Example**: "Find stocks with bullish golden cross and positive momentum"
# MAGIC
# MAGIC ## 3. Price Pattern Embeddings
# MAGIC - **Source**: `price_history` + `ticker_metrics` tables
# MAGIC - **Text generation**: Price movement narrative with trends
# MAGIC - **Use case**: Find tickers with similar price behavior
# MAGIC - **Example**: "Find stocks trading near 52-week high with strong volume"
# MAGIC
# MAGIC **Embedding model**: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
# MAGIC **Storage**: Lakebase Postgres with pgvector extension

# COMMAND ----------

# DBTITLE 1,Install dependencies
# MAGIC %pip uninstall -y psycopg2 psycopg2-binary
# MAGIC %pip install -q 'databricks-sdk>=0.118.0' sentence-transformers trafilatura requests pandas

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

# DBTITLE 1,Config
# Source tables
TICKER_DETAILS_TABLE = "ticker_details"
PRICE_HISTORY_TABLE = "price_history"
TICKER_METRICS_TABLE = "ticker_metrics"
TECHNICAL_INDICATORS_TABLE = "technical_indicators"

# Destination embedding tables
COMPANY_DESC_EMBEDDINGS_TABLE = "ticker_company_embeddings"
TECHNICAL_STATE_EMBEDDINGS_TABLE = "ticker_technical_embeddings"
PRICE_PATTERN_EMBEDDINGS_TABLE = "ticker_price_embeddings"

# Embedding model configuration
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

print(f"Configuration:")
print(f"  Source tables: {TICKER_DETAILS_TABLE}, {PRICE_HISTORY_TABLE}, {TICKER_METRICS_TABLE}, {TECHNICAL_INDICATORS_TABLE}")
print(f"  Embedding tables:")
print(f"    - {COMPANY_DESC_EMBEDDINGS_TABLE} (company descriptions)")
print(f"    - {TECHNICAL_STATE_EMBEDDINGS_TABLE} (technical indicators)")
print(f"    - {PRICE_PATTERN_EMBEDDINGS_TABLE} (price patterns)")
print(f"  Embedding model: {EMBEDDING_MODEL_NAME}")
print(f"  Vector dimension: {EMBEDDING_DIM}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Connect to Lakebase
# MAGIC
# MAGIC Resolve the Lakebase connection URL from Databricks secrets (same pattern as news embeddings notebook).

# COMMAND ----------

# DBTITLE 1,Parse Lakebase connection
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

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # 1. Company Description Embeddings
# MAGIC
# MAGIC Direct text embedding from `ticker_details.description` field.
# MAGIC
# MAGIC **Use case**: Semantic search for companies by business description  
# MAGIC **Example queries**: 
# MAGIC - "Find companies working on AI chips"
# MAGIC - "Find semiconductor manufacturers"
# MAGIC - "Find companies in social media"

# COMMAND ----------

# DBTITLE 1,Load company descriptions
import pandas as pd
import psycopg2

# Load ticker details with descriptions
conn = psycopg2.connect(
    host=db_host,
    port=db_port,
    dbname=db_name,
    user=db_user,
    password=db_password,
    sslmode='require'
)

try:
    query = f"""
        SELECT 
            symbol,
            name,
            description,
            market,
            primary_exchange,
            type
        FROM {TICKER_DETAILS_TABLE}
        WHERE description IS NOT NULL 
          AND TRIM(description) != ''
    """
    
    company_df = pd.read_sql_query(query, conn)
    print(f"Loaded {len(company_df)} companies with descriptions")
    display(company_df.head(3))
finally:
    conn.close()

# COMMAND ----------

# DBTITLE 1,Compute company description embeddings
import os
from sentence_transformers import SentenceTransformer
from datetime import datetime

# Set up HuggingFace cache
os.environ["HF_HOME"] = "/tmp/huggingface"
os.environ["TRANSFORMERS_CACHE"] = "/tmp/huggingface"
os.environ["HF_HUB_CACHE"] = "/tmp/huggingface"

print(f"Loading embedding model {EMBEDDING_MODEL_NAME}...")
model = SentenceTransformer(EMBEDDING_MODEL_NAME, cache_folder="/tmp/huggingface")

# Compute embeddings in batches
print("Computing embeddings for company descriptions...")
batch_size = 32
all_embeddings = []

for i in range(0, len(company_df), batch_size):
    batch = company_df.iloc[i:i+batch_size]
    vectors = model.encode(batch["description"].tolist(), show_progress_bar=False)
    all_embeddings.extend(vectors.tolist())

# Create embeddings DataFrame
company_embeddings_df = pd.DataFrame({
    "symbol": company_df["symbol"],
    "name": company_df["name"],
    "embedding_text": company_df["description"],
    "embedding": all_embeddings,
    "model_name": EMBEDDING_MODEL_NAME,
    "embedded_at": datetime.now()
})

print(f"✅ Computed {len(company_embeddings_df)} embeddings")
display(company_embeddings_df[["symbol", "name", "embedding_text"]].head(3))

# COMMAND ----------

# DBTITLE 1,Upsert company embeddings to Lakebase
from psycopg2.extras import execute_values

company_rows = company_embeddings_df.to_dict('records')

if len(company_rows) > 0:
    print(f"Upserting {len(company_rows)} company embeddings into {COMPANY_DESC_EMBEDDINGS_TABLE}...")
    
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
        
        # Create table if not exists
        create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {COMPANY_DESC_EMBEDDINGS_TABLE} (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                embedding_text TEXT,
                embedding double precision[],
                model_name TEXT,
                embedded_at TIMESTAMP
            )
        """
        cursor.execute(create_table_sql)
        
        # Prepare data tuples
        insert_data = [
            (
                row['symbol'],
                row['name'],
                row['embedding_text'],
                '{' + ','.join(str(float(x)) for x in row['embedding']) + '}',
                row['model_name'],
                row['embedded_at']
            )
            for row in company_rows
        ]
        
        # Upsert with ON CONFLICT UPDATE
        insert_sql = f"""
            INSERT INTO {COMPANY_DESC_EMBEDDINGS_TABLE} (
                symbol, name, embedding_text, embedding, model_name, embedded_at
            ) VALUES %s
            ON CONFLICT (symbol) DO UPDATE SET
                name = EXCLUDED.name,
                embedding_text = EXCLUDED.embedding_text,
                embedding = EXCLUDED.embedding,
                model_name = EXCLUDED.model_name,
                embedded_at = EXCLUDED.embedded_at
        """
        
        template = "(%s, %s, %s, %s::double precision[], %s, %s)"
        execute_values(cursor, insert_sql, insert_data, template=template, page_size=100)
        
        conn.commit()
        print(f"✅ Successfully upserted {len(company_rows)} company embeddings")
        
    finally:
        cursor.close()
        conn.close()
else:
    print("No company embeddings to write.")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # 2. Technical State Embeddings
# MAGIC
# MAGIC Generate technical narratives from indicator values (SMA, EMA, MACD, RSI).
# MAGIC
# MAGIC **Use case**: Find tickers with similar technical patterns  
# MAGIC **Example queries**:
# MAGIC - "Find stocks with bullish golden cross and positive momentum"
# MAGIC - "Find oversold stocks with RSI below 30"
# MAGIC - "Find stocks with MACD bullish crossover"
# MAGIC
# MAGIC **Technical State Narrative Template**:  
# MAGIC `"{SYMBOL} technical state as of {DATE}: RSI at {RSI} ({overbought/neutral/oversold}), SMA50 ({SMA50}) vs SMA200 ({SMA200}) showing {golden cross/death cross/neutral}, MACD at {MACD} with {positive/negative} momentum, EMA12 ({EMA12}) vs EMA26 ({EMA26})"`

# COMMAND ----------

# DBTITLE 1,Load technical indicators
conn = psycopg2.connect(
    host=db_host,
    port=db_port,
    dbname=db_name,
    user=db_user,
    password=db_password,
    sslmode='require'
)

try:
    # The technical_indicators table is in long format (one row per indicator value)
    # We need to pivot it to get one row per ticker with all indicators as columns
    query = f"""
        WITH latest_indicators AS (
            SELECT 
                ticker,
                indicator_type,
                window_size,
                value,
                signal,
                histogram,
                timestamp_ms,
                ROW_NUMBER() OVER (PARTITION BY ticker, indicator_type, window_size ORDER BY timestamp_ms DESC) as rn
            FROM {TECHNICAL_INDICATORS_TABLE}
        )
        SELECT 
            ticker as symbol,
            MAX(CASE WHEN indicator_type = 'SMA' AND window_size = 50 THEN value END) as sma_50,
            MAX(CASE WHEN indicator_type = 'SMA' AND window_size = 200 THEN value END) as sma_200,
            MAX(CASE WHEN indicator_type = 'EMA' AND window_size = 12 THEN value END) as ema_12,
            MAX(CASE WHEN indicator_type = 'EMA' AND window_size = 26 THEN value END) as ema_26,
            MAX(CASE WHEN indicator_type = 'MACD' THEN value END) as macd,
            MAX(CASE WHEN indicator_type = 'MACD' THEN signal END) as macd_signal,
            MAX(CASE WHEN indicator_type = 'MACD' THEN histogram END) as macd_histogram,
            MAX(CASE WHEN indicator_type = 'RSI' AND window_size = 14 THEN value END) as rsi_14,
            TO_TIMESTAMP(MAX(timestamp_ms) / 1000.0) as calculated_at
        FROM latest_indicators
        WHERE rn = 1
        GROUP BY ticker
    """
    
    technical_df = pd.read_sql_query(query, conn)
    
    print(f"Loaded technical indicators for {len(technical_df)} tickers")
    display(technical_df.head(3))
finally:
    conn.close()

# COMMAND ----------

# DBTITLE 1,Generate technical narratives
def generate_technical_narrative(row) -> str:
    """
    Generate natural language description of technical state.
    
    Example output:
    "NVDA technical state as of 2026-08-09: RSI at 65.3 showing slight 
    overbought conditions, SMA50 (150.5) crossed above SMA200 (145.2) 
    indicating bullish golden cross pattern, MACD at 2.3 with positive 
    momentum (histogram: 0.8), EMA12 (152.1) above EMA26 (148.3) showing 
    short-term bullish trend"
    """
    symbol = row['symbol']
    date = row['calculated_at'].strftime('%Y-%m-%d') if pd.notna(row['calculated_at']) else 'unknown date'
    
    # RSI analysis
    rsi = row['rsi_14']
    if pd.notna(rsi):
        if rsi > 70:
            rsi_desc = f"RSI at {rsi:.1f} showing overbought conditions"
        elif rsi < 30:
            rsi_desc = f"RSI at {rsi:.1f} showing oversold conditions"
        else:
            rsi_desc = f"RSI at {rsi:.1f} in neutral zone"
    else:
        rsi_desc = "RSI data unavailable"
    
    # SMA cross analysis (Golden/Death Cross)
    sma50 = row['sma_50']
    sma200 = row['sma_200']
    if pd.notna(sma50) and pd.notna(sma200):
        if sma50 > sma200:
            sma_desc = f"SMA50 ({sma50:.2f}) above SMA200 ({sma200:.2f}) indicating bullish golden cross pattern"
        elif sma50 < sma200:
            sma_desc = f"SMA50 ({sma50:.2f}) below SMA200 ({sma200:.2f}) indicating bearish death cross pattern"
        else:
            sma_desc = f"SMA50 ({sma50:.2f}) at SMA200 ({sma200:.2f}) showing neutral alignment"
    else:
        sma_desc = "SMA cross data unavailable"
    
    # MACD momentum analysis
    macd = row['macd']
    macd_hist = row['macd_histogram']
    if pd.notna(macd) and pd.notna(macd_hist):
        momentum = "positive" if macd_hist > 0 else "negative"
        macd_desc = f"MACD at {macd:.2f} with {momentum} momentum (histogram: {macd_hist:.2f})"
    else:
        macd_desc = "MACD data unavailable"
    
    # EMA trend analysis
    ema12 = row['ema_12']
    ema26 = row['ema_26']
    if pd.notna(ema12) and pd.notna(ema26):
        if ema12 > ema26:
            ema_desc = f"EMA12 ({ema12:.2f}) above EMA26 ({ema26:.2f}) showing short-term bullish trend"
        elif ema12 < ema26:
            ema_desc = f"EMA12 ({ema12:.2f}) below EMA26 ({ema26:.2f}) showing short-term bearish trend"
        else:
            ema_desc = f"EMA12 ({ema12:.2f}) at EMA26 ({ema26:.2f}) showing neutral trend"
    else:
        ema_desc = "EMA trend data unavailable"
    
    # Combine all descriptions
    narrative = f"{symbol} technical state as of {date}: {rsi_desc}, {sma_desc}, {macd_desc}, {ema_desc}"
    return narrative

# Generate narratives for all tickers
print("Generating technical narratives...")
technical_df['narrative'] = technical_df.apply(generate_technical_narrative, axis=1)

print(f"✅ Generated {len(technical_df)} technical narratives")
print("\nExample narratives:")
for i, row in technical_df.head(2).iterrows():
    print(f"\n{row['symbol']}:")
    print(f"  {row['narrative']}")

# COMMAND ----------

# DBTITLE 1,Compute technical state embeddings
print("Computing embeddings for technical narratives...")

# Compute embeddings in batches
all_embeddings = []
for i in range(0, len(technical_df), batch_size):
    batch = technical_df.iloc[i:i+batch_size]
    vectors = model.encode(batch["narrative"].tolist(), show_progress_bar=False)
    all_embeddings.extend(vectors.tolist())

# Create embeddings DataFrame
technical_embeddings_df = pd.DataFrame({
    "symbol": technical_df["symbol"],
    "calculated_at": technical_df["calculated_at"],
    "embedding_text": technical_df["narrative"],
    "rsi_14": technical_df["rsi_14"],
    "sma_50": technical_df["sma_50"],
    "sma_200": technical_df["sma_200"],
    "macd": technical_df["macd"],
    "embedding": all_embeddings,
    "model_name": EMBEDDING_MODEL_NAME,
    "embedded_at": datetime.now()
})

print(f"✅ Computed {len(technical_embeddings_df)} embeddings")

# COMMAND ----------

# DBTITLE 1,Upsert technical embeddings to Lakebase
technical_rows = technical_embeddings_df.to_dict('records')

if len(technical_rows) > 0:
    print(f"Upserting {len(technical_rows)} technical embeddings into {TECHNICAL_STATE_EMBEDDINGS_TABLE}...")
    
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
        
        # Create table if not exists
        create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {TECHNICAL_STATE_EMBEDDINGS_TABLE} (
                symbol TEXT PRIMARY KEY,
                calculated_at TIMESTAMP,
                embedding_text TEXT,
                rsi_14 DOUBLE PRECISION,
                sma_50 DOUBLE PRECISION,
                sma_200 DOUBLE PRECISION,
                macd DOUBLE PRECISION,
                embedding double precision[],
                model_name TEXT,
                embedded_at TIMESTAMP
            )
        """
        cursor.execute(create_table_sql)
        
        # Prepare data tuples
        insert_data = [
            (
                row['symbol'],
                row['calculated_at'],
                row['embedding_text'],
                float(row['rsi_14']) if pd.notna(row['rsi_14']) else None,
                float(row['sma_50']) if pd.notna(row['sma_50']) else None,
                float(row['sma_200']) if pd.notna(row['sma_200']) else None,
                float(row['macd']) if pd.notna(row['macd']) else None,
                '{' + ','.join(str(float(x)) for x in row['embedding']) + '}',
                row['model_name'],
                row['embedded_at']
            )
            for row in technical_rows
        ]
        
        # Upsert with ON CONFLICT UPDATE
        insert_sql = f"""
            INSERT INTO {TECHNICAL_STATE_EMBEDDINGS_TABLE} (
                symbol, calculated_at, embedding_text, rsi_14, sma_50, sma_200, macd,
                embedding, model_name, embedded_at
            ) VALUES %s
            ON CONFLICT (symbol) DO UPDATE SET
                calculated_at = EXCLUDED.calculated_at,
                embedding_text = EXCLUDED.embedding_text,
                rsi_14 = EXCLUDED.rsi_14,
                sma_50 = EXCLUDED.sma_50,
                sma_200 = EXCLUDED.sma_200,
                macd = EXCLUDED.macd,
                embedding = EXCLUDED.embedding,
                model_name = EXCLUDED.model_name,
                embedded_at = EXCLUDED.embedded_at
        """
        
        template = "(%s, %s, %s, %s, %s, %s, %s, %s::double precision[], %s, %s)"
        execute_values(cursor, insert_sql, insert_data, template=template, page_size=100)
        
        conn.commit()
        print(f"✅ Successfully upserted {len(technical_rows)} technical embeddings")
        
    finally:
        cursor.close()
        conn.close()
else:
    print("No technical embeddings to write.")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # 3. Price Pattern Embeddings
# MAGIC
# MAGIC Generate price movement narratives combining recent price history trends with current metrics.
# MAGIC
# MAGIC **Use case**: Find tickers with similar price behavior  
# MAGIC **Example queries**:
# MAGIC - "Find stocks trading near 52-week high with strong volume"
# MAGIC - "Find stocks with consistent uptrend over last week"
# MAGIC - "Find stocks with declining momentum and low volume"
# MAGIC
# MAGIC **Price Pattern Narrative Template**:  
# MAGIC `"{SYMBOL} as of {DATE}: Last close ${CLOSE} ({CHANGE}% {up/down} ${CHANGE_AMOUNT}), volume {VOLUME}M shares ({vs avg}), trading {near/below/above} 52-week high of ${HIGH}, showing {trend} over last {DAYS} days with avg daily gain of {AVG_GAIN}%"`

# COMMAND ----------

# DBTITLE 1,Load price history and metrics
conn = psycopg2.connect(
    host=db_host,
    port=db_port,
    dbname=db_name,
    user=db_user,
    password=db_password,
    sslmode='require'
)

try:
    # Load recent price history (last 30 days)
    history_query = f"""
        SELECT 
            symbol,
            date,
            open,
            high,
            low,
            close,
            volume
        FROM {PRICE_HISTORY_TABLE}
        WHERE date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY symbol, date DESC
    """
    
    price_history_df = pd.read_sql_query(history_query, conn)
    
    # Load current ticker metrics
    metrics_query = f"""
        SELECT 
            symbol,
            last_price as day_close,
            day_high,
            day_low,
            volume as day_volume,
            prev_close as prev_day_close,
            updated_at
        FROM {TICKER_METRICS_TABLE}
    """
    
    ticker_metrics_df = pd.read_sql_query(metrics_query, conn)
    
    print(f"Loaded price history: {len(price_history_df)} records for {price_history_df['symbol'].nunique()} tickers")
    print(f"Loaded current metrics: {len(ticker_metrics_df)} tickers")
    
finally:
    conn.close()

# COMMAND ----------

# DBTITLE 1,Generate price pattern narratives
def generate_price_narrative(symbol: str, history_df: pd.DataFrame, metrics_row: pd.Series) -> str:
    """
    Generate natural language description of price pattern.
    
    Example output:
    "AAPL as of 2026-08-09: Last close $180.50, up 2.5% (+$4.50) from 
    previous close, volume 50.2M shares (120% of 7-day average), trading 
    5% below 52-week high of $189.80, showing strong uptrend over last 
    7 days with average daily gain of 1.2%, price range $175-$185"
    """
    # Get symbol's price history
    symbol_history = history_df[history_df['symbol'] == symbol].sort_values('date', ascending=False)
    
    if len(symbol_history) == 0:
        return f"{symbol}: No price history available"
    
    # Current price info
    current_price = metrics_row['day_close']
    prev_close = metrics_row['prev_day_close']
    current_volume = metrics_row['day_volume']
    
    # Calculate price change
    if pd.notna(prev_close) and prev_close > 0:
        price_change = current_price - prev_close
        price_change_pct = (price_change / prev_close) * 100
        direction = "up" if price_change > 0 else "down"
        change_desc = f"{direction} {abs(price_change_pct):.1f}% ({'+' if price_change > 0 else ''}{price_change:.2f})"
    else:
        change_desc = "no previous close available"
    
    # Volume analysis (vs 7-day average)
    recent_7d = symbol_history.head(7)
    if len(recent_7d) > 1:
        avg_volume_7d = recent_7d['volume'].mean()
        if avg_volume_7d > 0:
            volume_vs_avg_pct = (current_volume / avg_volume_7d) * 100
            volume_desc = f"volume {current_volume/1e6:.1f}M shares ({volume_vs_avg_pct:.0f}% of 7-day avg)"
        else:
            volume_desc = f"volume {current_volume/1e6:.1f}M shares"
    else:
        volume_desc = f"volume {current_volume/1e6:.1f}M shares"
    
    # 52-week high/low
    if len(symbol_history) > 0:
        week_52_high = symbol_history['high'].max()
        week_52_low = symbol_history['low'].min()
        
        if pd.notna(week_52_high) and week_52_high > 0:
            distance_from_high_pct = ((current_price - week_52_high) / week_52_high) * 100
            if abs(distance_from_high_pct) < 5:
                high_desc = f"trading near 52-week high of ${week_52_high:.2f}"
            elif distance_from_high_pct > 0:
                high_desc = f"trading {distance_from_high_pct:.1f}% above previous 52-week high of ${week_52_high:.2f}"
            else:
                high_desc = f"trading {abs(distance_from_high_pct):.1f}% below 52-week high of ${week_52_high:.2f}"
        else:
            high_desc = "52-week high unavailable"
    else:
        high_desc = "52-week range unavailable"
    
    # Trend analysis (last 7 days)
    if len(recent_7d) >= 7:
        recent_closes = recent_7d['close'].tolist()
        recent_closes.reverse()  # oldest to newest
        
        # Calculate daily changes
        daily_changes = []
        for i in range(1, len(recent_closes)):
            if recent_closes[i-1] > 0:
                daily_change_pct = ((recent_closes[i] - recent_closes[i-1]) / recent_closes[i-1]) * 100
                daily_changes.append(daily_change_pct)
        
        if daily_changes:
            avg_daily_gain = sum(daily_changes) / len(daily_changes)
            
            # Determine trend
            positive_days = sum(1 for x in daily_changes if x > 0)
            if positive_days >= 5:
                trend = "strong uptrend"
            elif positive_days >= 4:
                trend = "uptrend"
            elif positive_days <= 2:
                trend = "downtrend"
            else:
                trend = "mixed trend"
            
            trend_desc = f"showing {trend} over last {len(daily_changes)} days with avg daily change of {avg_daily_gain:+.2f}%"
        else:
            trend_desc = "insufficient data for trend analysis"
    else:
        trend_desc = "insufficient history for 7-day trend"
    
    # Price range (last 7 days)
    if len(recent_7d) > 0:
        recent_low = recent_7d['low'].min()
        recent_high = recent_7d['high'].max()
        range_desc = f"7-day range ${recent_low:.2f}-${recent_high:.2f}"
    else:
        range_desc = "no recent range data"
    
    # Assemble narrative
    date = metrics_row['updated_at'].strftime('%Y-%m-%d') if pd.notna(metrics_row['updated_at']) else 'unknown date'
    
    narrative = (
        f"{symbol} as of {date}: Last close ${current_price:.2f} ({change_desc}), "
        f"{volume_desc}, {high_desc}, {trend_desc}, {range_desc}"
    )
    
    return narrative

# Generate narratives for all tickers with metrics
print("Generating price pattern narratives...")
narratives = []

for _, metrics_row in ticker_metrics_df.iterrows():
    symbol = metrics_row['symbol']
    narrative = generate_price_narrative(symbol, price_history_df, metrics_row)
    narratives.append({
        'symbol': symbol,
        'narrative': narrative,
        'current_price': metrics_row['day_close'],
        'day_volume': metrics_row['day_volume'],
        'updated_at': metrics_row['updated_at']
    })

price_narratives_df = pd.DataFrame(narratives)

print(f"✅ Generated {len(price_narratives_df)} price narratives")
print("\nExample narratives:")
for i, row in price_narratives_df.head(2).iterrows():
    print(f"\n{row['symbol']}:")
    print(f"  {row['narrative']}")

# COMMAND ----------

# DBTITLE 1,Compute price pattern embeddings
print("Computing embeddings for price narratives...")

# Compute embeddings in batches
all_embeddings = []
for i in range(0, len(price_narratives_df), batch_size):
    batch = price_narratives_df.iloc[i:i+batch_size]
    vectors = model.encode(batch["narrative"].tolist(), show_progress_bar=False)
    all_embeddings.extend(vectors.tolist())

# Create embeddings DataFrame
price_embeddings_df = pd.DataFrame({
    "symbol": price_narratives_df["symbol"],
    "updated_at": price_narratives_df["updated_at"],
    "embedding_text": price_narratives_df["narrative"],
    "current_price": price_narratives_df["current_price"],
    "day_volume": price_narratives_df["day_volume"],
    "embedding": all_embeddings,
    "model_name": EMBEDDING_MODEL_NAME,
    "embedded_at": datetime.now()
})

print(f"✅ Computed {len(price_embeddings_df)} embeddings")

# COMMAND ----------

# DBTITLE 1,Upsert price pattern embeddings to Lakebase
price_rows = price_embeddings_df.to_dict('records')

if len(price_rows) > 0:
    print(f"Upserting {len(price_rows)} price embeddings into {PRICE_PATTERN_EMBEDDINGS_TABLE}...")
    
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
        
        # Create table if not exists
        create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {PRICE_PATTERN_EMBEDDINGS_TABLE} (
                symbol TEXT PRIMARY KEY,
                updated_at TIMESTAMP,
                embedding_text TEXT,
                current_price DOUBLE PRECISION,
                day_volume BIGINT,
                embedding double precision[],
                model_name TEXT,
                embedded_at TIMESTAMP
            )
        """
        cursor.execute(create_table_sql)
        
        # Prepare data tuples
        insert_data = [
            (
                row['symbol'],
                row['updated_at'],
                row['embedding_text'],
                float(row['current_price']) if pd.notna(row['current_price']) else None,
                int(row['day_volume']) if pd.notna(row['day_volume']) else None,
                '{' + ','.join(str(float(x)) for x in row['embedding']) + '}',
                row['model_name'],
                row['embedded_at']
            )
            for row in price_rows
        ]
        
        # Upsert with ON CONFLICT UPDATE
        insert_sql = f"""
            INSERT INTO {PRICE_PATTERN_EMBEDDINGS_TABLE} (
                symbol, updated_at, embedding_text, current_price, day_volume,
                embedding, model_name, embedded_at
            ) VALUES %s
            ON CONFLICT (symbol) DO UPDATE SET
                updated_at = EXCLUDED.updated_at,
                embedding_text = EXCLUDED.embedding_text,
                current_price = EXCLUDED.current_price,
                day_volume = EXCLUDED.day_volume,
                embedding = EXCLUDED.embedding,
                model_name = EXCLUDED.model_name,
                embedded_at = EXCLUDED.embedded_at
        """
        
        template = "(%s, %s, %s, %s, %s, %s::double precision[], %s, %s)"
        execute_values(cursor, insert_sql, insert_data, template=template, page_size=100)
        
        conn.commit()
        print(f"✅ Successfully upserted {len(price_rows)} price embeddings")
        
    finally:
        cursor.close()
        conn.close()
else:
    print("No price embeddings to write.")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Summary & Usage
# MAGIC
# MAGIC This notebook created three types of embeddings, all using the same 384-dimensional vector space:
# MAGIC
# MAGIC ## Created Tables
# MAGIC
# MAGIC 1. **`ticker_company_embeddings`**  
# MAGIC    - Company descriptions embedded directly
# MAGIC    - Use for: Semantic company search
# MAGIC    - Example: "Find semiconductor companies"
# MAGIC
# MAGIC 2. **`ticker_technical_embeddings`**  
# MAGIC    - Technical indicator narratives (RSI, SMA, MACD, EMA)
# MAGIC    - Use for: Pattern matching by technical state
# MAGIC    - Example: "Find stocks with golden cross pattern"
# MAGIC
# MAGIC 3. **`ticker_price_embeddings`**  
# MAGIC    - Price movement narratives with trends and volume
# MAGIC    - Use for: Pattern matching by price behavior
# MAGIC    - Example: "Find stocks near 52-week high with strong volume"
# MAGIC
# MAGIC ## Querying Embeddings
# MAGIC
# MAGIC All three tables use the same pgvector infrastructure. Example similarity search:
# MAGIC
# MAGIC ```sql
# MAGIC -- Find companies similar to NVIDIA by description
# MAGIC SELECT 
# MAGIC     symbol, 
# MAGIC     name,
# MAGIC     embedding_text,
# MAGIC     1 - (embedding <=> (SELECT embedding FROM ticker_company_embeddings WHERE symbol = 'NVDA')) AS similarity
# MAGIC FROM ticker_company_embeddings
# MAGIC WHERE symbol != 'NVDA'
# MAGIC ORDER BY similarity DESC
# MAGIC LIMIT 5;
# MAGIC
# MAGIC -- Find stocks with similar technical state to META
# MAGIC SELECT 
# MAGIC     symbol,
# MAGIC     embedding_text,
# MAGIC     rsi_14,
# MAGIC     1 - (embedding <=> (SELECT embedding FROM ticker_technical_embeddings WHERE symbol = 'META')) AS similarity
# MAGIC FROM ticker_technical_embeddings
# MAGIC WHERE symbol != 'META'
# MAGIC ORDER BY similarity DESC
# MAGIC LIMIT 5;
# MAGIC
# MAGIC -- Find stocks with similar price patterns to AAPL
# MAGIC SELECT 
# MAGIC     symbol,
# MAGIC     embedding_text,
# MAGIC     current_price,
# MAGIC     1 - (embedding <=> (SELECT embedding FROM ticker_price_embeddings WHERE symbol = 'AAPL')) AS similarity
# MAGIC FROM ticker_price_embeddings
# MAGIC WHERE symbol != 'AAPL'
# MAGIC ORDER BY similarity DESC
# MAGIC LIMIT 5;
# MAGIC ```
# MAGIC
# MAGIC ## Cross-Modal Search
# MAGIC
# MAGIC Since all embeddings use the same model and vector space, you can search across types:
# MAGIC
# MAGIC ```sql
# MAGIC -- Find companies whose business description matches a technical pattern query
# MAGIC SELECT 
# MAGIC     c.symbol,
# MAGIC     c.name,
# MAGIC     c.embedding_text as company_description,
# MAGIC     t.embedding_text as technical_state,
# MAGIC     1 - (c.embedding <=> t.embedding) AS cross_modal_similarity
# MAGIC FROM ticker_company_embeddings c
# MAGIC JOIN ticker_technical_embeddings t ON c.symbol = t.symbol
# MAGIC ORDER BY cross_modal_similarity DESC;
# MAGIC ```
# MAGIC
# MAGIC ## Next Steps
# MAGIC
# MAGIC 1. **Enable pgvector extension** (if not already done):
# MAGIC    ```sql
# MAGIC    CREATE EXTENSION IF NOT EXISTS vector;
# MAGIC    ```
# MAGIC
# MAGIC 2. **Cast embeddings to vector type** for each table:
# MAGIC    ```sql
# MAGIC    UPDATE ticker_company_embeddings 
# MAGIC    SET embedding = embedding::vector 
# MAGIC    WHERE embedding IS NOT NULL;
# MAGIC    
# MAGIC    UPDATE ticker_technical_embeddings 
# MAGIC    SET embedding = embedding::vector 
# MAGIC    WHERE embedding IS NOT NULL;
# MAGIC    
# MAGIC    UPDATE ticker_price_embeddings 
# MAGIC    SET embedding = embedding::vector 
# MAGIC    WHERE embedding IS NOT NULL;
# MAGIC    ```
# MAGIC
# MAGIC 3. **Create indexes** for faster similarity search:
# MAGIC    ```sql
# MAGIC    CREATE INDEX ON ticker_company_embeddings USING ivfflat (embedding vector_cosine_ops);
# MAGIC    CREATE INDEX ON ticker_technical_embeddings USING ivfflat (embedding vector_cosine_ops);
# MAGIC    CREATE INDEX ON ticker_price_embeddings USING ivfflat (embedding vector_cosine_ops);
# MAGIC    ```

# COMMAND ----------


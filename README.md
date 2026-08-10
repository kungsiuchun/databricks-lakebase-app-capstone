# Financial Data Platform with Lakebase & MCP Agent

A production-ready Databricks application that provides comprehensive financial market data analysis using:
- **Lakebase** (Databricks-managed Postgres with pgvector) for operational data storage
- **MASSIVE API** (https://api.massive.io) for real-time and historical market data
- **Sentence Transformers** for semantic news embeddings
- **Flask web application** with interactive UI for ticker analysis and portfolio tracking
- **MCP Agent** for AI-powered stock research with vector search, news analysis, and persistent research notes
- **Automated ETL pipelines** for continuous data ingestion and processing

## Architecture Overview

This platform combines three core components:

1. **Flask Web Application** - User-facing API and web interface for:
   - Managing watchlists (add/remove tickers)
   - Viewing ticker details, price history, and metrics
   - Comparing tickers against benchmark (SPY)
   - Real-time news with semantic search capabilities
   - Interactive charts and visualizations

2. **Automated Data Pipelines** - Three notebooks scheduled as Databricks Workflows:
   - **Price & Company Data** (`ingest_ticker_data`) - Historical OHLCV, company profiles, market metrics
   - **News & Embeddings** (`ingest_ticker_news_embeddings`) - News articles with vector embeddings for semantic search
   - **Technical Indicators** (`ingest_ticker_technical_indicators`) - SMA, EMA, MACD, RSI calculations

3. **Lakebase Database** - Postgres with 11 core tables:
   - `watchlist` - User ticker selections
   - `ticker_details` - Company profiles (name, description, market cap, industry)
   - `price_history` - Historical OHLCV data (symbol, date, timespan composite PK)
   - `ticker_metrics` - Current price, volume, market data
   - `ticker_news_documents` - Raw news articles
   - `ticker_news_embeddings` - News title/description vectors (pgvector)
   - `ticker_news_chunk_embeddings` - Full article body chunks (for RAG)
   - `technical_indicators` - SMA, EMA, MACD, RSI time series
   - `research_notes` - AI agent research insights with sources and metadata
   - `price_alerts` - Alert rules with trigger conditions and notification settings
   - `user_activity` - Audit trail of user and agent actions

## Project Structure

### Core Application
- **`app.py`** - Flask web server with API endpoints:
  - `GET /` - Main UI dashboard
  - `GET /healthz` - Health check
  - `GET /records?limit=100` - Read synced records
  - `POST /sync` - Trigger data sync from Massive API
  - `GET /watchlist` - Get user's watchlist with latest prices
  - `POST /watchlist` - Add ticker to watchlist
  - `DELETE /watchlist/<symbol>` - Remove ticker
  - `POST /news/sync` - Sync news for specific tickers
  - `GET /ticker/<symbol>` - Full ticker details page
  - `GET /ticker/<symbol>/compare` - Compare ticker vs benchmark (SPY)
- **`lakebase.py`** - Lakebase connection manager (psycopg2 pooling, context managers)
- **`massive_client.py`** - Massive API client with methods:
  - `get_ticker_details()` - Company profile
  - `get_price_history()` - Historical OHLCV data
  - `get_current_metrics()` - Real-time price snapshot
  - `get_news()` - News articles with pagination
  - `get_sma()`, `get_ema()`, `get_macd()`, `get_rsi()` - Technical indicators
- **`setup_secrets.py`** - One-time setup script for Databricks secrets
- **`app.yaml`** - Databricks App deployment configuration

### ETL Notebooks (`notebooks/`)
1. **`ingest_ticker_data.py`** - Comprehensive ticker data pipeline:
   - Reads watchlist symbols from Lakebase
   - Fetches company details, 90 days of price history, current metrics
   - Upserts into `ticker_details`, `price_history`, `ticker_metrics`
   - Rate-limited (5 req/min for free tier)

2. **`ingest_ticker_news_embeddings.py`** - News & semantic search pipeline:
   - Fetches news articles for watchlisted tickers
   - Generates embeddings using `sentence-transformers/all-MiniLM-L6-v2`
   - Creates both title/description vectors and full-article chunk vectors
   - Stores in `ticker_news_documents`, `ticker_news_embeddings`, `ticker_news_chunk_embeddings`
   - Enables semantic news search and RAG applications

3. **`ingest_ticker_technical_indicators.py`** - Technical analysis pipeline:
   - Computes SMA (50d, 200d), EMA (12d, 26d), MACD, RSI (14d)
   - Stores time-series indicators in `technical_indicators` table
   - Supports trend analysis and trading signals

### Web UI (`templates/` & `static/`)
- **`templates/index.html`** - Main dashboard with watchlist management
- **`templates/ticker_detail.html`** - Individual ticker analysis page
- **`static/chart.js`** - Price chart visualizations (Chart.js integration)

### Database Setup (`sql/`)
- **`01_setup_news_table.sql`** - News documents table
- **`02_setup_embeddings_table.sql`** - Title/description embeddings (pgvector)
- **`03_setup_chunk_embeddings_table.sql`** - Full article chunk embeddings
- **`04_cast_arrays_to_vectors.sql`** - Convert array columns to pgvector format
- **`05_setup_ticker_details_table.sql`** - Company profiles
- **`06_setup_price_history_table.sql`** - Historical OHLCV data (with timespan PK)
- **`07_setup_ticker_metrics_table.sql`** - Current market metrics
- **`08_add_industry_columns.sql`** - Industry classification fields
- **`09_setup_technical_indicators_table.sql`** - Technical analysis indicators
- **`10_setup_research_notes_table.sql`** - AI agent research insights (for MCP agent)
- **`11_setup_price_alerts_table.sql`** - Price alert rules (for MCP agent)
- **`12_setup_user_activity_table.sql`** - Activity tracking and audit logs (for MCP agent)

### Deployment (`databricks.yml` & `resources/`)
- **`databricks.yml`** - Declarative Automation Bundle (DAB) configuration
- **`resources/ingest_ticker_news_embeddings_job.yml`** - Scheduled workflow definition

### MCP Agent (`mcp_server/` & `AGENT_DEMO.md`)
- **`mcp_server/massive_mcp_server.py`** - MCP server exposing AI agent tools:
  - `vector_search` - Semantic search over news and technical embeddings
  - `get_news` - Fetch recent news with sentiment analysis
  - `get_ticker_details` - Company profile and fundamentals
  - `save_research_note` - Persist agent insights to `research_notes` table
  - `add_to_watchlist` - Add stocks to user's tracking list
  - `get_price_history` - Historical OHLCV data retrieval
- **`mcp_server/AGENT_SYSTEM_PROMPT.md`** - System prompt and agent behavior guidelines
- **`AGENT_DEMO.md`** - Full demo transcript showing:
  - End-to-end agent workflow (vector search → news → research note → watchlist)
  - Multi-tool orchestration with clear reasoning
  - Source citations and transparent decision-making
  - Agent configuration and deployment steps

> **See `AGENT_DEMO.md`** for detailed examples of the agent in action, including comparative stock analysis, sentiment tracking, and research note creation with full source attribution.

## Step-by-step setup

### 1. Get a Massive API key

1. Go to [https://massive.com](https://massive.com) and sign up for a free account.
2. Navigate to your account **Settings** → **API Keys** (or **Developer** section).
3. Click **Create API Key** or **Generate New Key**.
4. Give it a name (e.g., `databricks-finance-app`) and copy the generated key immediately — it may only be shown once.
5. Keep this key secure — you'll store it in Databricks secrets in step 3.

> **Free Tier Limits**: 5 API requests per minute. The notebooks include rate limiting (`time.sleep(12)` between requests) to stay within quota. For production workloads, consider upgrading to a paid tier.

### 2. Create a Lakebase instance and a native-password role

1. In your Databricks workspace, go to **Catalog** (left sidebar) and select the **Lakebase** tab (or search "Lakebase" in the workspace search bar).
2. Click **Create Lakebase instance** (sometimes labeled **Create database instance**).
   - Give it a name (e.g. `massive-sync-db`).
   - Choose the capacity/compute size and region appropriate for your workload (defaults are fine to start).
   - Click **Create** and wait for the instance to reach the **Available**/**Running** state.
3. Open the newly created instance, then go to the **Roles & Databases** tab (sometimes called **Permissions** or **Roles**).
4. **Enable native (password) authentication** for the instance if it isn't already on:
   - Look for an authentication setting such as **Native passwords** or **Password authentication** and toggle/enable it. By default some Lakebase instances only support OAuth/token-based auth — you need password auth enabled so the role below gets a static password instead of a short-lived token.
5. **Create a new role**:
   - Click **Add role** / **Create role**.
   - Choose **Password** as the authentication method (not OAuth).
   - Name the role (e.g. `massive_app`) and let Databricks generate (or set) a password.
6. **Copy the connection URL** shown for the role. It will look like:

   ```
   postgresql://<role>:<password>@<host>.database.cloud.databricks.com:5432/databricks_postgres?sslmode=require
   ```

   Keep this URL — you'll paste it into `setup_secrets.py`'s prompt in the next step.

### 3. Store your secrets

Run once from a **Databricks notebook** or terminal in your workspace:

```python
%sh python setup_secrets.py
```

This securely prompts for (via `getpass` - no echoing to logs):
- **Massive API key** → stored as `massive/api-key`
- **Lakebase connection URL** → stored as `database/lakebase-url` (base64 encoded)

Both secrets are then available to the Flask app and notebooks via the Databricks secrets API.

### 4. Configure environment variables (local dev)

Copy `.env.example` to `.env` and paste your Lakebase URL as `LAKEBASE_URL` for local runs:

```bash
cp .env.example .env
```

For deployment, `app.yaml` already pulls `LAKEBASE_URL` from the `database/lakebase-url` secret automatically — no manual editing needed there.

### 5. Install dependencies

```bash
pip install -r requirements.txt
```

### 6. Run locally (optional - for development)

For local development and testing:

```bash
python app.py
```

The app will start on `http://localhost:5000`. 

**Note**: Local development requires:
- Valid `.env` file with `LAKEBASE_URL`
- Network access to your Lakebase instance
- Massive API key in environment

### 7. Create a Git folder in Databricks and deploy the app (no CLI required)

All of this is done through the Databricks workspace UI:

1. **Create a Git folder**:
   - In the Databricks workspace sidebar, click **Workspace** > **Create** > **Git folder** (in older UIs this is called **Repos** > **Add Repo**).
   - Paste the Git URL of this project's repository (e.g. your GitHub/GitLab remote for this codebase).
   - Choose a folder name and click **Create Git folder**. Databricks will clone the repo directly into your workspace — this becomes the source for your app.

2. **Create the Databricks App**:
   - In the sidebar, go to **Compute** > **Apps** (or search "Apps" in the workspace search bar).
   - Click **Create app**, then choose **Custom** (or "From scratch").
   - Give the app a name (e.g. `massive-lakebase-sync`).

3. **Point the app at your Git folder**:
   - When prompted for the source code location, select **Workspace files** / **Git folder** and browse to the Git folder you created in step 1 (the folder containing `app.py` and `app.yaml`).
   - Databricks will read `app.yaml` from that folder automatically to configure the `command` and `env` (including the `LAKEBASE_URL`, `MASSIVE_API_BASE_URL`, and secret scope/key references).

4. **Deploy**:
   - Click **Deploy** (or **Create and deploy**) in the Apps UI. Databricks will build and start the app using the Git folder's current contents — no `databricks` CLI commands are needed.
   - Whenever you update the code, pull the latest changes into the Git folder (**Git folder** > **Pull**, via the UI) and click **Deploy** again in the Apps UI to redeploy.

5. Once deployed, open the app's URL from the Apps UI and hit `GET /healthz` to confirm it's running, then try `POST /sync` to pull data from Massive into Lakebase.

## API Endpoints

### Public Endpoints (Web UI)
- **`GET /`** - Main dashboard with watchlist and ticker search
- **`GET /ticker/<symbol>`** - Detailed ticker page (price chart, news, metrics, technical indicators)
- **`GET /ticker/<symbol>/compare`** - Compare ticker against SPY benchmark

### Protected Endpoints (require `X-API-Key` header)
- **`GET /healthz`** - Health check (returns database connection status)
- **`GET /records?limit=100`** - Read synced records from Lakebase
- **`POST /sync`** - Trigger full data sync (details, history, metrics) for watchlisted tickers
- **`POST /news/sync`** - Sync news articles
  - Optional body: `{"tickers": ["AAPL", "MSFT"], "limit": 50}`
  - Defaults to watchlisted tickers if no body provided

### Watchlist Endpoints (Public - used by UI)
- **`GET /watchlist`** - Get user's watchlist with latest prices
- **`POST /watchlist`** - Add ticker to watchlist
  - Body: `{"symbol": "AAPL"}`
- **`DELETE /watchlist/<symbol>`** - Remove ticker from watchlist

### Authentication & Rate Limiting
- **API Key**: Set via `API_KEYS` environment variable (comma-separated for multiple keys)
- **Rate Limit**: 5 requests per minute on protected endpoints
- **Default Dev Key**: `default-dev-key-change-in-production` (⚠️ CHANGE IN PRODUCTION!)

### Example API Usage

```bash
# Add a ticker to watchlist
curl -X POST http://localhost:5000/watchlist \
  -H "Content-Type: application/json" \
  -d '{"symbol": "NVDA"}'

# Trigger sync (requires API key)
curl -X POST http://localhost:5000/sync \
  -H "X-API-Key: your-api-key-here"

# Fetch news for specific tickers (requires API key)
curl -X POST http://localhost:5000/news/sync \
  -H "X-API-Key: your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["AAPL", "TSLA"], "limit": 100}'
```

## Semantic Search (BETA)

The app includes an **AI-powered semantic search** feature that searches across company data, news articles, technical indicators, and price patterns using vector embeddings.

### Access
- **Web UI**: `GET /search` - Interactive search interface
- **API**: `POST /api/semantic_search` - JSON endpoint for programmatic access
- **Diagnostics**: `GET /api/semantic_search/test` - Health check for all dependencies

### Requirements

Semantic search depends on several components that must be set up first:

1. **pgvector extension** in Lakebase:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

2. **Embedding tables** must be populated by running these notebooks:
   - `notebooks/ingest_ticker_news_embeddings.py` → creates `ticker_news_embeddings`
   - `notebooks/ingest_price_pattern_embeddings.py` → creates `ticker_price_embeddings`
   - `notebooks/ingest_ticker_technical_indicators.py` → creates `ticker_technical_embeddings`
   - Company embeddings table → `ticker_company_embeddings`

3. **Databricks Foundation Model endpoints** must be accessible:
   - `databricks-gte-large-en` (for query embeddings)
   - `databricks-meta-llama-3-1-70b-instruct` (for AI summaries)

### Testing

**Check system status:**
```bash
curl http://localhost:8000/api/semantic_search/test
```

This returns the status of all components:
- Database connection
- pgvector extension
- Embedding tables (existence + row counts)
- Embedding endpoint
- LLM endpoint

**Run a test search:**
```bash
curl -X POST http://localhost:8000/api/semantic_search \
  -H "Content-Type: application/json" \
  -d '{"query": "semiconductor companies with strong growth", "top_k": 10}'
```

### Expected Response Format

```json
{
  "success": true,
  "ai_summary": "AI-generated analysis of the results...",
  "results": {
    "query": "semiconductor companies with strong growth",
    "num_tickers": 5,
    "tickers": [
      {
        "symbol": "NVDA",
        "max_similarity": 0.87,
        "sources": [
          {
            "source_table": "ticker_company_embeddings",
            "similarity": 0.87,
            "name": "NVIDIA Corporation",
            "embedding_text": "Designs GPUs for gaming and AI..."
          },
          {
            "source_table": "ticker_news_embeddings",
            "similarity": 0.82,
            "article_title": "NVIDIA Reports Strong Q4 Earnings",
            "sentiment_score": 0.9
          }
        ]
      }
    ]
  }
}
```

### Sample Queries

- `"AI chip companies with bullish momentum"`
- `"semiconductor stocks with positive news"`
- `"technology companies with bearish technical indicators"`
- `"renewable energy stocks with high volume"`

### Troubleshooting

If you get a 500 error:

1. **Run the diagnostic endpoint first**: `GET /api/semantic_search/test`
2. **Check the errors array** in the response - it will tell you exactly what's missing
3. **Common issues**:
   - **pgvector not installed**: Run `CREATE EXTENSION vector;` in your Lakebase database
   - **Embedding tables don't exist**: Run the embedding generation notebooks listed above
   - **Tables are empty**: The notebooks ran but didn't process any tickers - check your watchlist has data
   - **Embedding endpoint unavailable**: The `databricks-gte-large-en` endpoint isn't accessible from your workspace

### Architecture

The semantic search pipeline:
1. User submits natural language query
2. Query is embedded using `databricks-gte-large-en` (1024-dim vector)
3. Vector similarity search across 4 embedding tables using pgvector's `<=>` operator
4. Results grouped by ticker, sorted by max similarity
5. Top results passed to `databricks-meta-llama-3-1-70b-instruct` for summary generation

## Scheduling ETL Pipelines as Databricks Workflows

All three notebooks can be scheduled as Databricks Workflows to keep your data fresh. Each is self-contained with configurable widgets for parameters.

### Pipeline 1: Ticker Data Ingestion
**Notebook**: `notebooks/ingest_ticker_data.py`  
**Purpose**: Sync company details, price history (90 days), and current market metrics  
**Recommended Schedule**: Daily at 6:00 PM ET (after market close)  
**Output Tables**: `ticker_details`, `price_history`, `ticker_metrics`

### Pipeline 2: News & Embeddings
**Notebook**: `notebooks/ingest_ticker_news_embeddings.py`  
**Purpose**: Fetch news articles, generate semantic embeddings for search  
**Recommended Schedule**: Every 4 hours  
**Output Tables**: `ticker_news_documents`, `ticker_news_embeddings`, `ticker_news_chunk_embeddings`

### Pipeline 3: Technical Indicators
**Notebook**: `notebooks/ingest_ticker_technical_indicators.py`  
**Purpose**: Calculate SMA, EMA, MACD, RSI for trend analysis  
**Recommended Schedule**: Daily at 6:30 PM ET (after price data sync)  
**Output Tables**: `technical_indicators`

---

You can schedule these two ways — pick whichever fits your workflow:

### Option A: Declarative Automation Bundle (DAB) - Recommended

**Benefits**: Version-controlled, reproducible across workspaces, CI/CD-friendly

This repo includes a starter DAB config for the news pipeline (`databricks.yml` + `resources/ingest_ticker_news_embeddings_job.yml`). Extend it for the other two notebooks:

1. **Update workspace URL** in `databricks.yml`:
   ```yaml
   workspace:
     host: https://your-workspace.cloud.databricks.com
   ```

2. **Deploy the bundle**:
   ```bash
   databricks bundle deploy -t dev
   ```

3. **Test the job manually**:
   ```bash
   databricks bundle run ingest_ticker_news_embeddings_job -t dev
   ```

4. **Enable the schedule**: Once validated, edit `resources/ingest_ticker_news_embeddings_job.yml`:
   ```yaml
   pause_status: UNPAUSED  # Change from PAUSED
   ```
   Then redeploy: `databricks bundle deploy -t dev`

5. **Add jobs for the other notebooks**: Copy the YAML template and adjust:
   - `resources/ingest_ticker_data_job.yml` - Schedule for daily 6:00 PM ET
   - `resources/ingest_technical_indicators_job.yml` - Schedule for daily 6:30 PM ET

**Pro Tip**: Use DAB for production deployments. It supports multiple environments (dev/staging/prod) and integrates with Git workflows.

### Option B: Workflows UI (Quick Start - No CLI)

Create jobs directly in the Databricks UI. Repeat these steps for each of the three notebooks:

#### General Steps (apply to all three notebooks):

1. **Navigate**: **Workflows** (sidebar) → **Jobs** → **Create Job**

2. **Task Configuration**:
   - **Task type**: Notebook
   - **Notebook path**: Browse to `notebooks/<notebook_name>.py`
   - **Cluster**: 
     - **Recommended**: New job cluster (1-2 workers, latest DBR/MLR)
     - **Alternative**: Serverless (if available in your workspace)

3. **Schedule**: Click **Add trigger** → **Scheduled**

4. **Notifications**: Add email for on-failure alerts

5. **Test**: Click **Run now** before enabling the schedule

---

#### Job 1: Ticker Data Ingestion
**Notebook**: `notebooks/ingest_ticker_data.py`  
**Schedule**: Daily at 6:00 PM ET (`0 0 18 * * ? America/New_York`)  
**Parameters** (click **Add** under Parameters):
- `watchlist_table_name` = `watchlist`
- `details_table_name` = `ticker_details`
- `history_table_name` = `price_history`
- `metrics_table_name` = `ticker_metrics`
- `massive_secret_scope` = `massive`
- `massive_secret_key` = `api-key`
- `massive_api_base_url` = `https://api.massive.io`
- `history_days` = `90`
- `rate_limit_delay_seconds` = `12`

#### Job 2: News & Embeddings
**Notebook**: `notebooks/ingest_ticker_news_embeddings.py`  
**Schedule**: Every 4 hours (`0 0 */4 * * ?`)  
**Parameters**:
- `watchlist_table_name` = `watchlist`
- `news_table_name` = `ticker_news_documents`
- `embeddings_table_name` = `ticker_news_embeddings`
- `chunk_embeddings_table_name` = `ticker_news_chunk_embeddings`
- `embedding_model` = `sentence-transformers/all-MiniLM-L6-v2`
- `massive_secret_scope` = `massive`
- `massive_secret_key` = `api-key`
- `massive_api_base_url` = `https://api.massive.io`
- `news_fetch_limit` = `50`
- `max_requests_per_minute` = `5`
- `chunk_size` = `800`
- `chunk_overlap` = `100`

#### Job 3: Technical Indicators
**Notebook**: `notebooks/ingest_ticker_technical_indicators.py`  
**Schedule**: Daily at 6:30 PM ET (`0 30 18 * * ? America/New_York`)  
**Parameters**:
- `watchlist_table_name` = `watchlist`
- `indicators_table_name` = `technical_indicators`
- `massive_secret_scope` = `massive`
- `massive_secret_key` = `api-key`
- `massive_api_base_url` = `https://api.massive.io`
- `max_requests_per_minute` = `5`
- `data_limit_per_indicator` = `100`

---

**When to use each approach**:
- **DAB (Option A)**: Production deployments, multi-environment (dev/staging/prod), CI/CD pipelines
- **UI (Option B)**: Quick prototyping, demos, personal projects

## Enabling Change Data Feed (CDF) for Postgres tables

Lakebase supports **Change Data Feed (CDF)**, a managed way to stream row-level inserts/updates/deletes
from your Lakebase Postgres tables into Unity Catalog Delta tables (no Debezium, no custom connectors).
CDF is enabled per-**schema** in the `databricks_postgres` database, and every table in that schema that
meets two conditions is picked up automatically: it has `REPLICA IDENTITY FULL` set, and it has at least
one row.

> **Note:** CDF is only available on paid Databricks accounts — it is not supported on the free
> Databricks Community Edition or trial tier.

### 1. Set `REPLICA IDENTITY FULL` on the tables you want to track

By default, Postgres only logs primary-key columns on change. To capture full row contents (needed for
CDF), enable `REPLICA IDENTITY FULL` on each table — including `watchlist` and `massive_records` from
this app:

```sql
ALTER TABLE watchlist REPLICA IDENTITY FULL;
ALTER TABLE massive_records REPLICA IDENTITY FULL;
```

Run this once per table, either from a Databricks SQL editor connected to your Lakebase instance, or
from a `psql` session using your `LAKEBASE_URL`. Any new table you add later (e.g. via `ensure_table`-style
helpers in `app.py`) needs the same `ALTER TABLE ... REPLICA IDENTITY FULL` statement run once before it
will be included in the feed. Tables with the setting but zero rows are skipped until the first row is
inserted, then picked up automatically.

You can confirm which tables currently qualify by querying:

```sql
SELECT * FROM wal2delta.tables;
```

### 2. Start CDF from the Lakebase UI

1. In your Databricks workspace, open the **Lakebase** tab for your instance.
2. Go to **Lakebase CDF** and click **Start**.
3. Select the `databricks_postgres` database and the schema containing your tables (the default
   schema, `public`, works — it's inside `databricks_postgres`).
4. Choose the Unity Catalog destination schema/catalog where the CDF history tables should land.
5. Confirm — the UI shows a preview of qualifying tables (e.g. `watchlist`, `massive_records`) and
   their sync status before you start.

Once running, each qualifying table gets a corresponding Delta table named `lb_<table_name>_history`
(e.g. `lb_watchlist_history`) in Unity Catalog, updated roughly every 15 seconds. Each row includes
metadata columns (`_pg_change_type`, `_pg_lsn`, `_pg_xid`, `_timestamp`, `_sort_by`) describing the
change, so downstream Delta Live Tables/pipelines can build Silver/Gold layers off the append-only
history.

> **Note:** Disabling CDF is lossy — changes made while it's off aren't captured, and re-enabling
> triggers a full resync (every row reloaded as an `insert`). There's no per-table exclusion option
> within an enabled schema; the only way to keep a table out of the feed is to not set
> `REPLICA IDENTITY FULL` on it.

## Key Features

### 1. Real-Time Market Data
- **Price History**: 90 days of OHLCV data per ticker
- **Company Profiles**: Name, description, market cap, industry, employee count
- **Current Metrics**: Real-time price, volume, daily change, market cap
- **Benchmark Comparison**: Compare any ticker against SPY (S&P 500)

### 2. Semantic News Search
- **Vector Embeddings**: News titles and descriptions embedded using Sentence Transformers
- **Full-Text RAG**: Article bodies chunked and embedded for retrieval-augmented generation
- **pgvector Integration**: Native Postgres vector similarity search
- **Use Cases**: 
  - "Show me recent news similar to this article"
  - "What are investors saying about AI?"
  - Build chatbots that cite recent market news

### 3. Technical Analysis
- **Moving Averages**: SMA (50d, 200d), EMA (12d, 26d)
- **Momentum Indicators**: MACD (12/26/9), RSI (14d)
- **Trend Signals**: Golden cross, death cross, overbought/oversold
- **Time Series Storage**: Historical indicator values for backtesting

### 4. Security & Production-Ready
- **API Key Authentication**: Protect sync endpoints from unauthorized access
- **Rate Limiting**: 5 req/min on protected routes (in-memory, upgrade to Redis for multi-instance)
- **Connection Pooling**: Efficient Lakebase connection management via `psycopg2.pool`
- **Error Handling**: Comprehensive logging and graceful fallbacks
- **Environment-Based Config**: Separate dev/prod configurations via `databricks.yml`

### 5. Change Data Capture (CDF)
Lakebase supports streaming row-level changes from Postgres to Unity Catalog Delta tables. See [Enabling CDF](#enabling-change-data-feed-cdf-for-postgres-tables) below for setup.

---

## Technical Notes

### Authentication
- **Lakebase**: Single `LAKEBASE_URL` secret with native Postgres role (static password, no rotation needed)
- **Massive API**: API key stored in `massive/api-key` secret (base64 encoded)
- **Databricks**: Secrets fetched via `WorkspaceClient().secrets.get_secret()`

### Rate Limiting
- **Massive API Free Tier**: 5 API calls per minute (enforced in notebooks via `time.sleep(12)`)
- **Flask App**: In-memory rate limiter (5 req/min per API key/IP)
- **Production Upgrade**: Replace in-memory store with Redis for distributed rate limiting

### Performance Optimization
- **Batch Upserts**: Use `psycopg2.extras.execute_values()` for bulk inserts (100x faster than row-by-row)
- **Connection Pooling**: `lakebase.py` uses `psycopg2.pool.SimpleConnectionPool` (min=1, max=10)
- **Async Embeddings**: Consider `sentence-transformers` batching for faster embedding generation
- **Indexes**: Automatic indexes on ticker symbols, dates, and vector columns

### Extending the Platform

**Add new data sources**:
1. Add methods to `massive_client.py` (e.g., `get_options_data()`, `get_crypto_prices()`)
2. Create corresponding tables in `sql/`
3. Build a new notebook in `notebooks/` to ingest the data
4. Schedule as a Databricks Workflow

**Add new analysis endpoints**:
1. Define routes in `app.py` (e.g., `@app.route("/ticker/<symbol>/options")`)
2. Query Lakebase via `lakebase.run_query()`
3. Render in HTML template or return JSON

**Build a RAG chatbot**:
1. Use `ticker_news_chunk_embeddings` for semantic search
2. Query: `SELECT * FROM ticker_news_chunk_embeddings ORDER BY embedding <=> %s LIMIT 5`
3. Pass retrieved chunks to an LLM (OpenAI, Anthropic, Databricks Foundation Models)
4. Cite sources using `article_url` and `published_utc`

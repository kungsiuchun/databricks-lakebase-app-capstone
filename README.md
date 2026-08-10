# Stock Watcher

Stock Watcher is a Databricks application for researching public equities.

It combines a browser-based dashboard for people with a separate MCP server for agents.

Both surfaces use the same Massive market-data client and the same Lakebase-backed watchlist.

The dashboard is for browsing, searching, and tracking symbols.

The MCP server is for an agent that needs current market data without scraping the UI.

## What this project does

- Lets a signed-in user build a personal stock watchlist.
- Shows company details, current metrics, price history, recent news, and SPY comparison.
- Fetches market data from Massive using a Databricks-managed secret.
- Stores dashboard data in Lakebase PostgreSQL.
- Exposes a small, typed, read-only MCP tool surface for agents.
- Includes an optional scheduled job that creates news embeddings in Lakebase.

This is not a trading system.

It does not place orders, move money, or expose a generic proxy to the Massive API.

## Two applications, one data client

The repository contains two entrypoints.

They should be deployed as separate Databricks Apps.

| Application | Entrypoint | Audience | Purpose |
| --- | --- | --- | --- |
| Web dashboard | `app.py` | Human users | Browse tickers and manage watchlists. |
| MCP server | `mcp_server/massive_mcp_server.py` | Agents | Query typed, read-only Massive tools. |

`massive_client.py` is the one canonical Massive client.

Do not copy it into the MCP directory or create a second implementation.

The current `app.yaml` launches the web dashboard.

It does not launch the MCP server.

## Web dashboard

The dashboard is a Flask application backed by Lakebase.

Start at `/` to see the watchlist.

Open `/ticker?symbol=NVDA` to view a ticker detail page.

The detail page includes company information, chart controls, recent news, and a comparison with SPY.

The initial chart range is the most recent 30 calendar days.

Users can choose 1D, 1W, 1M, 3M, 1Y, or YTD from the chart controls.

The browser never calls Massive directly.

It calls Flask, and Flask calls Massive with the server-side secret.

### Dashboard routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/` | `GET` | Watchlist page. |
| `/ticker` | `GET` | Ticker detail page. |
| `/healthz` | `GET` | Health check. |
| `/watchlist` | `GET` | Read the current user's watchlist. |
| `/watchlist` | `POST` | Add or refresh a watchlist symbol. |
| `/watchlist/<symbol>` | `DELETE` | Remove a watchlist symbol. |
| `/ticker/<symbol>/details` | `GET` | Company profile and branding data. |
| `/ticker/<symbol>/history` | `GET` | OHLC history for the chart. |
| `/ticker/<symbol>/metrics` | `GET` | Latest price and derived metrics. |
| `/ticker/<symbol>/news` | `GET` | Recent news for a symbol. |
| `/ticker/<symbol>/compare` | `GET` | Performance comparison against SPY. |
| `/logo/<symbol>` | `GET` | Proxied company logo. |

`GET /records`, `POST /sync`, and `POST /news/sync` are administrative operations.

They require an `X-API-Key` header and are rate limited.

### Chart requests

The dashboard requests chart data through this route:

```text
GET /ticker/<symbol>/history?days=<number>&limit=<number>
```

For the default 1M view, `days` is `30`.

Flask turns that value into a Massive aggregate range request.

The request uses daily bars and sends a `from` date and a `to` date in `YYYY-MM-DD` format.

YTD is intentionally different: it starts on January 1 of the server's current year.

If a chart is blank, first inspect the response from `/ticker/<symbol>/history`.

A Massive request can return `200 OK` while the Flask route still fails later when processing the response.

The Flask application log contains the traceback for that case.

## MCP server for agents

The MCP server gives an agent direct access to selected Massive capabilities.

It is intentionally narrower than the raw Massive API.

That keeps agent calls predictable, typed, and auditable.

The server runs over streamable HTTP.

It listens on `DATABRICKS_APP_PORT`, then `PORT`, then `8000`.

Register the external URL of the deployed MCP app with your MCP-compatible agent.

### Available MCP tools

#### `get_latest_price(symbol)`

Returns previous-session aggregate data for one ticker.

Use it for a fast latest-price lookup.

#### `get_news(ticker, limit=50, published_utc_gte=None)`

Returns recent Massive news articles for one ticker.

Use `published_utc_gte` to restrict results to a date or ISO timestamp.

#### `get_ticker_details(symbol)`

Returns company, exchange, classification, and branding data.

Use it when the agent needs basic company context.

#### `get_price_history(symbol, from_date, to_date, timespan="day", multiplier=1)`

Returns historical aggregate bars.

The caller supplies explicit inclusive start and end dates.

#### `get_sma(symbol, window=50, series_type="close", timespan="day", order="desc", limit=100)`

Returns Simple Moving Average values.

#### `get_ema(symbol, window=50, series_type="close", timespan="day", order="desc", limit=100)`

Returns Exponential Moving Average values.

#### `get_macd(symbol, short_window=12, long_window=26, signal_window=9, ...)`

Returns MACD values, including signal and histogram data when Massive provides them.

#### `get_rsi(symbol, window=14, series_type="close", timespan="day", order="desc", limit=100)`

Returns Relative Strength Index values.

The MCP server passes provider errors through instead of inventing fallback data.

## Data flow

```text
Browser ──> Flask dashboard ──> Massive API
                    │
                    └──────────> Lakebase PostgreSQL

Agent ───> Massive MCP server ─> Massive API
```

The dashboard reads cached data from Lakebase where available.

When a ticker is not cached, the dashboard can fetch Massive data directly and return it without saving it.

Adding a symbol to the watchlist triggers the fuller sync path.

That path fetches a latest price, company details, price history, and metrics before it saves the watchlist entry.

The MCP server does not write to Lakebase.

## Required secrets

Both applications read credentials from Databricks secret scopes through `WorkspaceClient`.

Create the following entries before you run or deploy either application.

| Scope | Key | Purpose |
| --- | --- | --- |
| `massive` | `api-key` | Massive API credential. |
| `database` | `lakebase-url` | Lakebase PostgreSQL connection URL. |

Grant the relevant Databricks App identity permission to read both scopes.

Do not commit API keys, database URLs, passwords, or tokens.

The `.env.example` file is not a replacement for Databricks SDK authentication.

Local processes still need an authenticated Databricks SDK session because the client reads the secret scopes at runtime.

## Run the web dashboard locally

Install the dashboard dependencies:

```powershell
pip install -r requirements.txt
```

Authenticate the Databricks SDK to a workspace that contains the required secrets.

Then start Flask:

```powershell
python app.py
```

Open the local URL printed by Flask.

Call `/healthz` to confirm that the process is running.

## Deploy the web dashboard

The committed `app.yaml` is the dashboard configuration.

Its command is:

```yaml
command:
  - python
  - app.py
```

Deploy this repository as a Databricks App after its secret permissions are configured.

Verify `/healthz` after every deployment.

Use the dashboard URL for people, not agents.

## Run the MCP server locally

FastMCP is required by `mcp_server/massive_mcp_server.py`.

It is not currently declared in `requirements.txt`.

Install it before starting the server:

```powershell
pip install -r requirements.txt fastmcp
python mcp_server/massive_mcp_server.py
```

The process must have the same Databricks SDK authentication and secret access as the dashboard.

## Deploy the MCP server

Create a second Databricks App for the MCP server.

Use the same Massive and Lakebase environment variables from the dashboard `app.yaml`.

Change only the command:

```yaml
command:
  - python
  - mcp_server/massive_mcp_server.py
```

Do not replace the dashboard command in the existing app if the dashboard must remain available.

After deployment, register the MCP app's external URL with the agent platform.

## Massive client behavior

`massive_client.py` owns authentication, HTTP calls, and rate limiting.

The API key is loaded from `massive/api-key` and sent as a Bearer token.

The default Massive base URL comes from `MASSIVE_API_BASE_URL`.

The dashboard App configuration sets it to `https://api.massive.com`.

The client defaults to five requests per minute.

It spaces requests evenly to avoid exceeding that limit.

This means a burst of agent or dashboard calls can wait instead of failing immediately.

Do not bypass this limiter with a second client implementation.

## Optional scheduled news ingestion

`notebooks/ingest_ticker_news_embeddings.py` reads watchlist tickers and fetches their news.

It writes raw news documents and vector embeddings to Lakebase.

`resources/ingest_ticker_news_embeddings_job.yml` defines the scheduled Databricks job.

The schedule is paused by default.

Configure the workspace host in `databricks.yml`.

Deploy the bundle, run the job manually once, inspect the result, then unpause the schedule.

## Project map

```text
app.py                              Flask routes, UI data flow, and sync logic
app.yaml                            Dashboard Databricks App configuration
lakebase.py                         Lakebase PostgreSQL connection helpers
massive_client.py                   Shared Massive API client
mcp_server/massive_mcp_server.py    Agent-facing FastMCP server
templates/                          HTML templates for the dashboard
static/js/chart.js                  Chart requests and chart rendering
static/js/detail.js                 Ticker detail page behavior
notebooks/                          Optional ingestion and embedding work
resources/                          Databricks Asset Bundle job definition
```

## Troubleshooting

### The chart says it failed to fetch price history

Check the response from `/ticker/<symbol>/history` first.

If Massive shows a successful request but the UI shows a Flask error, inspect the Databricks App logs.

The failure is then in the dashboard route after the provider response, not necessarily in the date range.

### The MCP server does not start

Confirm that FastMCP is installed.

Confirm that the process can authenticate to Databricks and read both secret scopes.

Confirm that the MCP deployment uses its own entrypoint instead of `app.py`.

### A request is slow

Check the Massive rate limiter before assuming the app is stuck.

The default limit deliberately spaces calls at five requests per minute.

### A secret lookup fails

Verify the scope name, key name, and App identity permission.

The expected names are `massive/api-key` and `database/lakebase-url`.

## Safety notes

Keep credentials out of the repository, browser code, and logs.

Treat the MCP server as a read-only research interface.

Keep dashboard deployment and MCP deployment as separate release units.

Do not claim a chart, sync, or MCP tool works in production until its deployed App has been checked.

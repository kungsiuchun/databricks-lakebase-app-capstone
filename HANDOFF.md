# Stock Watcher Dashboard - Project Handoff Document

## 🎯 Project Goal

Build a **premium SaaS-style stock tracking dashboard** with:
- Real-time ticker search and detailed company profiles
- Interactive price charts (TradingView-style candlesticks)
- Performance comparison vs S&P 500 benchmark
- Company news feed
- Personal watchlist management
- Automated daily data sync for tracked tickers

**Target:** 1920×1080 canvas, modern UI/UX, Databricks Lakebase backend

---

## 📊 Progress Overview

### ✅ COMPLETED FEATURES

#### **Backend Infrastructure**
- ✅ Lakebase Postgres database setup
- ✅ Polygon.io API client (`massive_client.py`)
  - Company details endpoint
  - Price history endpoint (OHLC data)
  - News endpoint
- ✅ Database tables created:
  - `ticker_details` - Company profiles (name, logo, description, market cap, etc.)
  - `price_history` - Historical OHLC price data
  - `ticker_metrics` - Current metrics (price, change %, volume)
  - `watchlist` - User-tracked tickers
  - `ticker_news_documents` - News articles
- ✅ Backend API endpoints (`app.py`):
  - `GET /watchlist` - List user's watchlist
  - `POST /watchlist` - Add ticker (triggers immediate data sync)
  - `DELETE /watchlist/<symbol>` - Remove ticker
  - `GET /ticker/<symbol>/details` - Company profile
  - `GET /ticker/<symbol>/history` - Historical prices
  - `GET /ticker/<symbol>/metrics` - Current metrics
  - `GET /ticker/<symbol>/compare` - **NEW!** Performance vs S&P 500 benchmark
- ✅ Daily batch sync job (`daily_ticker_sync.py`)
  - Auto-syncs SPY (S&P 500 benchmark) for comparisons
  - Updates price history and metrics for all watchlist tickers
  - Configurable rate limiting

#### **Frontend - Feature 2: Company Profile & Layout** ✅ COMPLETE
**Recent Bug Fixes (Session 2):**
- ✅ Fixed `price.toFixed is not a function` error (added `parseFloat()` for API numeric values)
- ✅ Removed top-right "Watchlist" button, added "← Back to Watchlist" link above company header
- ✅ Added company initials fallback for missing logos (e.g., "SOFI" → "SF" in blue gradient circle)
- ✅ Formatted IPO date as "MMM DD, YYYY" (removed time/timezone)
- ✅ **Fixed missing Industry field** - Added `sic_code` and `sic_description` columns to database
- ✅ **Fixed logo loading** - Added `/logo/<symbol>` proxy endpoint (Polygon logos require API key)
- ✅ Added tooltip to exchange badge (XNAS = NASDAQ)

### 🎯 **CRITICAL ARCHITECTURAL FIX** (Session 2)

**Problem Identified:** Search only worked for tickers already in watchlist. Users got 404 "Ticker not found" when searching new tickers.

**Root Cause:** Backend endpoints only queried database, no API fallback.

**Solution:** Implemented API fallback pattern on 3 endpoints:

1. **`/ticker/<symbol>/details`**
   - Try database first (fast for watchlist)
   - Fallback to Polygon API if not found
   - Returns data without saving

2. **`/ticker/<symbol>/metrics`**
   - Try database first
   - Fallback to Polygon API for current price
   - Calculates change from API data

3. **`/logo/<symbol>`**
   - Fetches logo from Polygon API directly
   - Proxies with API key
   - Works for any ticker

**New User Flow:**
```
Search "NVDA" → View full profile (from API)
             → Click "Add to Watchlist"
             → Saved to database
             → Future loads are faster (from DB cache)
```

**Impact:** Search now works for ANY ticker on Polygon, not just watchlist!

---


**Pages:**
- ✅ Watchlist page (`/` → `index.html`)
  - Search bar for ticker lookup
  - Grid of watchlist cards (clickable → detail page)
  - Add/remove tickers from watchlist
- ✅ Ticker detail page (`/ticker?symbol=XXX` → `ticker_detail.html`)
  - Top navigation with search
  - Company header (logo, name, real-time price, change %)
  - **"Add to Watchlist" button** with star icon (★/☆)
  - Company info grid (Market Cap, Employees, Industry, IPO Date, Type, Homepage)
  - Company description section
  - Placeholders for upcoming features (chart, news)
- ✅ Premium SaaS styling (`static/css/detail.css`)
- ✅ Interactive JavaScript (`static/js/detail.js`)
  - Parallel API loading
  - Watchlist state management
  - Toast notifications
  - Error handling

---

### 🚧 IN PROGRESS

None (Feature 1 complete, ready for next feature)

---

### 📝 TODO - Remaining Features

#### **Feature 1: Interactive Price Chart** 📊 (NEXT)
**Priority:** HIGH  
**Library:** Lightweight Charts (TradingView library)  
**Reference:** User provided image 1 (candlestick chart with volume)

**Requirements:**
- Candlestick/line chart with OHLC data from `GET /ticker/<symbol>/history`
- Volume bars at bottom
- Timeframe selector buttons (1D, 1W, 1M, 3M, 1Y, YTD)
- Chart type toggle (candlestick, line, area)
- Real-time price tooltip on hover
- Responsive + mobile-friendly

**Integration:**
- Replace placeholder in `ticker_detail.html` (section: "Price Chart")
- Add CDN script for Lightweight Charts
- Create `static/js/chart.js` for chart logic

---

#### **Feature 5: Recent News Feed** 📰
**Priority:** MEDIUM  
**Reference:** User requirement: "Company recent news"

**Requirements:**
- News cards with:
  - Article title + description
  - Publisher name + timestamp
  - Sentiment badge (if available)
  - Thumbnail image (if available)
  - Click to open article in new tab
- Scrollable list (latest 10-20 articles)
- Loading states

**Data Source:**
- Endpoint: `GET /news/sync` (already exists, syncs news to DB)
- Need new endpoint: `GET /ticker/<symbol>/news` to fetch from DB

**Integration:**
- Replace placeholder in `ticker_detail.html` (section: "Recent News")
- Create `static/js/news.js` for news loading

---

#### **Feature 6: Performance Comparison Chart** 🆚
**Priority:** HIGH (backend already done!)  
**Reference:** Leverages `/ticker/<symbol>/compare` endpoint

**Requirements:**
- Dual-line chart: Ticker vs SPY normalized returns
- Timeframe selector (30D, 90D, 1Y, YTD)
- Summary metrics display:
  - Alpha (outperformance %)
  - Volatility
  - Sharpe ratio
- Color-coded: Green if outperforming, Red if underperforming

**Integration:**
- Add new section in `ticker_detail.html` after price chart
- Use Chart.js or Lightweight Charts (same as Feature 1)

---

#### **Feature 3: Key Metrics vs Benchmark** 📊
**Priority:** LOW (nice-to-have)  
**Reference:** User provided image 2 (metrics comparison table)

**Requirements:**
- Side-by-side comparison table
- Metrics: P/E, PEG, Profit Margin, ROE, Revenue Growth
- Visual progress bars showing performance vs S&P 500 average
- Color coding (green = outperform, red = underperform)

**Challenge:**
- Requires **financial metrics data** (P/E ratio, profit margins, etc.)
- Polygon.io free tier has **limited financial data**
- May need to use `/ticker/<symbol>/compare` alpha as proxy

---

#### **Feature 4: Financial Trend Charts** 📈
**Priority:** SKIP (paid API required)  
**Reference:** User provided image 3 (quarterly profit + cash flow charts)

**Status:** ⏭️ SKIPPED  
**Reason:** Requires Polygon.io **Financials API** (paid tier)
- Quarterly profit/revenue data
- Operating & Free Cash Flow data
- Would need additional API endpoints + DB tables

**Alternative:** Focus on price-based metrics using free tier data

---

## 🏗️ Architecture

### Tech Stack
- **Backend:** Python Flask
- **Database:** Lakebase Postgres (Databricks-managed)
- **API:** Polygon.io (free tier)
- **Frontend:** Vanilla JS + HTML/CSS
- **Charts:** Lightweight Charts (TradingView)
- **Deployment:** Databricks Apps

### File Structure
```
databricks-lakebase-app-capstone/
├── app.py                          # Main Flask application
├── app.yaml                        # Databricks App config
├── lakebase.py                     # Lakebase DB connection helper
├── massive_client.py               # Polygon.io API client
├── daily_ticker_sync.py            # Batch sync job
├── sql/                            # DDL files (table creation)
│   ├── 05_setup_ticker_details_table.sql
│   ├── 06_setup_price_history_table.sql
│   └── 07_setup_ticker_metrics_table.sql
├── templates/
│   ├── index.html                  # Watchlist page
│   └── ticker_detail.html          # Detail page ✅ DONE
├── static/
│   ├── css/
│   │   └── detail.css              # Detail page styles ✅ DONE
│   └── js/
│       └── detail.js               # Detail page logic ✅ DONE
└── STOCK_WATCHER_GUIDE.md         # Comprehensive documentation
```

---

## 🔌 API Endpoints

### Frontend Routes
- `GET /` → Watchlist page (`index.html`)
- `GET /ticker?symbol=<SYMBOL>` → Detail page (`ticker_detail.html`)

### Backend API
| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `/watchlist` | GET | List user's watchlist | ✅ |
| `/watchlist` | POST | Add ticker to watchlist (triggers sync) | ✅ |
| `/watchlist/<symbol>` | DELETE | Remove ticker from watchlist | ✅ |
| `/ticker/<symbol>/details` | GET | Company profile (name, logo, description) | ✅ |
| `/ticker/<symbol>/history` | GET | Historical OHLC price data | ✅ |
| `/ticker/<symbol>/metrics` | GET | Current metrics (price, change %) | ✅ |
| `/ticker/<symbol>/compare` | GET | Performance vs SPY benchmark | ✅ NEW! |
| `/logo/<symbol>` | GET | Proxy company logo with API key | ✅ NEW! |
| `/ticker/<symbol>/news` | GET | Recent news articles | ⏳ TODO |
| `/news/sync` | POST | Sync news from Polygon API | ✅ |

---

## 🧪 Testing Instructions

### Local Development
1. Start Flask app:
   ```bash
   python app.py
   ```

2. Visit pages:
   - Watchlist: `http://localhost:8000/`
   - Detail: `http://localhost:8000/ticker?symbol=AAPL`

3. Test flow:
   - Search "AAPL" → Redirects to detail page
   - Click "Add to Watchlist" → Data syncs, button changes to "★ Remove"
   - Return to `/` → See AAPL in watchlist grid
   - Click AAPL card → Returns to detail page

### Test Tickers
- **AAPL** - Apple Inc. (tech)
- **MSFT** - Microsoft (tech)
- **GOOGL** - Google (tech)
- **TSLA** - Tesla (automotive)
- **SPY** - S&P 500 ETF (benchmark - always synced)

---

## 📦 Database Schema

### `ticker_details`
Company profile information
- `symbol` (PK), `name`, `description`, `logo_url`, `market_cap`, `homepage_url`, etc.

### `price_history`
Historical OHLC data
- `symbol`, `date` (composite PK), `open`, `high`, `low`, `close`, `volume`, `vwap`

### `ticker_metrics`
Current market metrics
- `symbol` (PK), `last_price`, `price_change`, `price_change_pct`, `volume`, etc.

### `watchlist`
User-tracked tickers
- `symbol`, `email` (composite PK), `latest_price`, `updated_at`

---

## 🚀 Next Steps (Priority Order)

1. ✅ **Feature 1: Interactive Price Chart** (NEXT)
   - Integrate Lightweight Charts library
   - Fetch data from `/ticker/<symbol>/history`
   - Add timeframe controls

2. ✅ **Feature 6: Performance vs S&P 500**
   - Leverage existing `/ticker/<symbol>/compare` endpoint
   - Dual-line comparison chart
   - Alpha/volatility display

3. ✅ **Feature 5: Recent News Feed**
   - Create `GET /ticker/<symbol>/news` endpoint
   - Render news cards
   - Link to full articles

4. ⏳ **Feature 3: Key Metrics vs Benchmark** (optional)
   - Depends on data availability
   - May simplify to use alpha as proxy

5. ⏭️ **Feature 4: Financial Trends** (skip)
   - Requires paid API tier

---

## 🎨 Design System

### Colors
- Primary Blue: `#3b82f6`
- Success Green: `#10b981`
- Danger Red: `#ef4444`
- Background: `#f9fafb`
- White: `#ffffff`
- Text Dark: `#111827`
- Text Gray: `#6b7280`

### Typography
- Font: Inter / System UI
- Headers: 24-32px bold
- Body: 14-16px regular
- Metrics: 20-24px semibold

---

## 🔑 Key Decisions

1. **Hybrid Data Flow:** Immediate fetch on "Add to Watchlist" + daily batch sync
2. **Free API Only:** Using Polygon.io free tier (5 calls/min limit)
3. **SPY as Benchmark:** Auto-synced for all comparison charts
4. **Chart Library:** Lightweight Charts (TradingView) for professional candlesticks
5. **Skip Financial Metrics:** Paid API required, focus on price-based analytics

---

## 📚 Documentation

- **STOCK_WATCHER_GUIDE.md** - Comprehensive guide (workflow, API usage, troubleshooting)
- **HANDOFF.md** - This document (progress tracking, context preservation)

---

## 🤝 Handoff Notes

**If resuming from a new session:**
1. Read this document first to understand progress
2. Feature 2 (Company Profile) is COMPLETE and working
3. Next: Build Feature 1 (Interactive Price Chart)
4. All backend endpoints are ready
5. Frontend just needs chart integration

**Current State:**
- ✅ Backend fully functional
- ✅ Navigation flow working (search → detail → watchlist → detail)
- ✅ Company profile page complete
- ⏳ Chart/news/comparison sections are placeholders

**Contact:**
User prefers: Complete one feature at a time, align before coding

---

Last Updated: 2025-01-XX (Feature 2 completed + Bug fixes)

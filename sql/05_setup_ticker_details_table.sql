-- Create ticker_details table for company profile information
-- This table caches company metadata that rarely changes (company name, description, logo, etc.)
-- Run this ONCE before using the watchlist feature with ticker details

CREATE TABLE IF NOT EXISTS ticker_details (
    symbol VARCHAR(10) PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    market VARCHAR(20),  -- e.g., "stocks", "crypto", "forex"
    locale VARCHAR(10),  -- e.g., "us", "global"
    primary_exchange VARCHAR(10),  -- e.g., "XNAS" (NASDAQ), "XNYS" (NYSE)
    type VARCHAR(10),  -- e.g., "CS" (Common Stock), "ETF", "ADR"
    active BOOLEAN DEFAULT true,
    currency_name VARCHAR(10),  -- e.g., "usd"
    cik VARCHAR(20),  -- SEC Central Index Key
    composite_figi VARCHAR(20),
    share_class_figi VARCHAR(20),
    market_cap BIGINT,  -- Market capitalization in USD
    phone_number VARCHAR(30),
    address_line1 TEXT,
    address_city VARCHAR(100),
    address_state VARCHAR(50),
    address_postal_code VARCHAR(20),
    sic_code VARCHAR(10),  -- Standard Industrial Classification code
    sic_description TEXT,
    homepage_url TEXT,
    total_employees INTEGER,
    list_date DATE,  -- IPO/listing date
    logo_url TEXT,
    icon_url TEXT,
    share_class_shares_outstanding BIGINT,
    weighted_shares_outstanding BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for faster lookups by symbol (primary key already indexed)
-- Add index for active tickers for filtering
CREATE INDEX IF NOT EXISTS idx_ticker_details_active ON ticker_details(active) WHERE active = true;

-- Add index for market cap sorting (useful for dashboards)
CREATE INDEX IF NOT EXISTS idx_ticker_details_market_cap ON ticker_details(market_cap DESC) WHERE market_cap IS NOT NULL;

-- Comments for documentation
COMMENT ON TABLE ticker_details IS 'Company profile and reference data from Polygon.io /v3/reference/tickers endpoint. Cached data that rarely changes.';
COMMENT ON COLUMN ticker_details.symbol IS 'Stock ticker symbol (e.g., AAPL, MSFT)';
COMMENT ON COLUMN ticker_details.market_cap IS 'Market capitalization in USD';
COMMENT ON COLUMN ticker_details.list_date IS 'Date the company went public (IPO date)';
COMMENT ON COLUMN ticker_details.logo_url IS 'URL to company logo from Polygon.io branding API';
COMMENT ON COLUMN ticker_details.updated_at IS 'Last time this record was refreshed from the API';
-- Create price_history table for historical OHLC (Open, High, Low, Close) data
-- This table stores daily price bars for charting and technical analysis
-- Run this ONCE before fetching historical price data

CREATE TABLE IF NOT EXISTS price_history (
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open NUMERIC(12, 4),  -- Opening price
    high NUMERIC(12, 4),  -- Highest price during the period
    low NUMERIC(12, 4),   -- Lowest price during the period
    close NUMERIC(12, 4), -- Closing price
    volume BIGINT,        -- Number of shares traded
    vwap NUMERIC(12, 4),  -- Volume-weighted average price
    transactions INTEGER, -- Number of transactions (if available)
    timestamp_ms BIGINT,  -- Unix timestamp in milliseconds from API
    timespan VARCHAR(10) DEFAULT 'day',  -- 'minute', 'hour', 'day', 'week', 'month'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date, timespan)
);

-- Index for efficient querying by symbol and date range (most common query pattern)
CREATE INDEX IF NOT EXISTS idx_price_history_symbol_date ON price_history(symbol, date DESC);

-- Index for querying by date across all symbols (useful for market-wide analysis)
CREATE INDEX IF NOT EXISTS idx_price_history_date ON price_history(date DESC);

-- Index for volume analysis (finding high-volume days)
CREATE INDEX IF NOT EXISTS idx_price_history_volume ON price_history(symbol, volume DESC) WHERE volume IS NOT NULL;

-- Foreign key constraint to ensure we only store history for tickers in watchlist
-- (Optional - comment out if you want to cache history for tickers not actively watched)
-- ALTER TABLE price_history ADD CONSTRAINT fk_price_history_symbol 
--     FOREIGN KEY (symbol) REFERENCES watchlist(symbol) ON DELETE CASCADE;

-- Comments for documentation
COMMENT ON TABLE price_history IS 'Historical OHLC price data from Polygon.io /v2/aggs endpoint. Used for charting and technical analysis.';
COMMENT ON COLUMN price_history.symbol IS 'Stock ticker symbol (e.g., AAPL, MSFT)';
COMMENT ON COLUMN price_history.date IS 'Trading date for this bar (YYYY-MM-DD)';
COMMENT ON COLUMN price_history.vwap IS 'Volume-weighted average price - more accurate than simple average';
COMMENT ON COLUMN price_history.timespan IS 'Bar interval: day (default), week, month, etc.';
COMMENT ON COLUMN price_history.timestamp_ms IS 'Unix timestamp in milliseconds from Polygon API';
COMMENT ON COLUMN price_history.updated_at IS 'Last time this record was refreshed (useful for detecting stale data)';
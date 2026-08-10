-- Create ticker_metrics table for current/latest market metrics
-- This table stores the most recent price, volume, market cap, and calculated metrics
-- Updated daily (or more frequently if using a paid Polygon.io tier with real-time data)
-- Run this ONCE before tracking ticker metrics

CREATE TABLE IF NOT EXISTS ticker_metrics (
    symbol VARCHAR(10) PRIMARY KEY,
    last_price NUMERIC(12, 4),      -- Most recent traded price
    prev_close NUMERIC(12, 4),      -- Previous day's closing price
    price_change NUMERIC(12, 4),    -- Absolute price change (last_price - prev_close)
    price_change_pct NUMERIC(8, 4), -- Percentage change ((last_price - prev_close) / prev_close * 100)
    day_open NUMERIC(12, 4),        -- Today's opening price
    day_high NUMERIC(12, 4),        -- Today's high
    day_low NUMERIC(12, 4),         -- Today's low
    volume BIGINT,                  -- Today's trading volume
    market_cap BIGINT,              -- Current market capitalization in USD
    shares_outstanding BIGINT,      -- Number of shares outstanding (from ticker_details)
    vwap NUMERIC(12, 4),            -- Today's volume-weighted average price
    fifty_two_week_high NUMERIC(12, 4),  -- 52-week high (calculated from price_history)
    fifty_two_week_low NUMERIC(12, 4),   -- 52-week low (calculated from price_history)
    avg_volume_30d BIGINT,          -- 30-day average volume (calculated from price_history)
    last_trade_timestamp BIGINT,    -- Unix timestamp (ms) of the last trade
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- Last time metrics were refreshed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for sorting by price change (to find biggest movers)
CREATE INDEX IF NOT EXISTS idx_ticker_metrics_price_change_pct ON ticker_metrics(price_change_pct DESC) WHERE price_change_pct IS NOT NULL;

-- Index for sorting by volume (to find most actively traded)
CREATE INDEX IF NOT EXISTS idx_ticker_metrics_volume ON ticker_metrics(volume DESC) WHERE volume IS NOT NULL;

-- Index for finding recently updated tickers
CREATE INDEX IF NOT EXISTS idx_ticker_metrics_updated_at ON ticker_metrics(updated_at DESC);

-- Foreign key constraint to ensure we only track metrics for valid tickers
-- (Optional - comment out if you want to cache metrics for tickers not in ticker_details)
-- ALTER TABLE ticker_metrics ADD CONSTRAINT fk_ticker_metrics_symbol 
--     FOREIGN KEY (symbol) REFERENCES ticker_details(symbol) ON DELETE CASCADE;

-- Comments for documentation
COMMENT ON TABLE ticker_metrics IS 'Current market metrics and key statistics from Polygon.io. Updated daily via batch job.';
COMMENT ON COLUMN ticker_metrics.symbol IS 'Stock ticker symbol (e.g., AAPL, MSFT)';
COMMENT ON COLUMN ticker_metrics.price_change_pct IS 'Daily percentage change: (current - prev_close) / prev_close * 100';
COMMENT ON COLUMN ticker_metrics.market_cap IS 'Market capitalization: last_price * shares_outstanding';
COMMENT ON COLUMN ticker_metrics.vwap IS 'Volume-weighted average price for today';
COMMENT ON COLUMN ticker_metrics.fifty_two_week_high IS '52-week high price (calculated from price_history table)';
COMMENT ON COLUMN ticker_metrics.avg_volume_30d IS '30-day average trading volume (calculated from price_history table)';
COMMENT ON COLUMN ticker_metrics.updated_at IS 'Timestamp of last metrics refresh - use this to detect stale data';
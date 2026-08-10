-- Technical Indicators Table Setup
-- Stores SMA, EMA, MACD, and RSI indicators for stock tickers from Polygon API
--
-- This table uses a flexible schema to accommodate multiple indicator types:
-- - SMA/EMA/RSI: use only the 'value' column
-- - MACD: uses 'value' (MACD line), 'signal' (signal line), and 'histogram' columns

CREATE TABLE IF NOT EXISTS technical_indicators (
    -- Primary identification
    ticker VARCHAR(10) NOT NULL,
    indicator_type VARCHAR(10) NOT NULL,  -- 'SMA', 'EMA', 'MACD', 'RSI'
    timestamp_ms BIGINT NOT NULL,
    timestamp_utc TIMESTAMP GENERATED ALWAYS AS (TO_TIMESTAMP(timestamp_ms / 1000)) STORED,
    
    -- Indicator parameters
    window_size INT,          -- For SMA/EMA/RSI (e.g., 50-day SMA, 14-day RSI)
    short_window INT,         -- For MACD only (default: 12)
    long_window INT,          -- For MACD only (default: 26)
    signal_window INT,        -- For MACD only (default: 9)
    series_type VARCHAR(10),  -- 'close', 'open', 'high', 'low'
    timespan VARCHAR(10),     -- 'day', 'week', 'month'
    
    -- Indicator values
    value DOUBLE PRECISION NOT NULL,  -- Primary indicator value (used by all types)
    signal DOUBLE PRECISION,          -- MACD signal line (MACD only)
    histogram DOUBLE PRECISION,       -- MACD histogram (MACD only)
    
    -- Metadata
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Composite primary key
    PRIMARY KEY (ticker, indicator_type, timestamp_ms, window_size)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_ticker_indicator_time 
    ON technical_indicators (ticker, indicator_type, timestamp_ms DESC);

CREATE INDEX IF NOT EXISTS idx_ticker_time 
    ON technical_indicators (ticker, timestamp_ms DESC);

CREATE INDEX IF NOT EXISTS idx_timestamp 
    ON technical_indicators (timestamp_ms DESC);

-- Comments for documentation
COMMENT ON TABLE technical_indicators IS 
    'Technical indicators (SMA, EMA, MACD, RSI) for stock tickers from Polygon.io API';

COMMENT ON COLUMN technical_indicators.ticker IS 
    'Stock ticker symbol (e.g., AAPL, GOOGL)';

COMMENT ON COLUMN technical_indicators.indicator_type IS 
    'Type of technical indicator: SMA, EMA, MACD, or RSI';

COMMENT ON COLUMN technical_indicators.timestamp_ms IS 
    'Unix timestamp in milliseconds from the API';

COMMENT ON COLUMN technical_indicators.timestamp_utc IS 
    'Human-readable UTC timestamp derived from timestamp_ms';

COMMENT ON COLUMN technical_indicators.window_size IS 
    'Window/period for SMA, EMA, or RSI (e.g., 50 for 50-day SMA, 14 for 14-day RSI)';

COMMENT ON COLUMN technical_indicators.value IS 
    'Primary indicator value: SMA/EMA average, MACD line, or RSI value';

COMMENT ON COLUMN technical_indicators.signal IS 
    'MACD signal line (9-day EMA of MACD) - NULL for other indicator types';

COMMENT ON COLUMN technical_indicators.histogram IS 
    'MACD histogram (MACD - signal) - NULL for other indicator types';
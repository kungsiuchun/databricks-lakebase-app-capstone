-- Create price_alerts table for price-based notifications
-- This table stores alert rules that can be evaluated against current market data
-- Run this ONCE before using price alert functionality

CREATE TABLE IF NOT EXISTS price_alerts (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,  -- 'price_above', 'price_below', 'percent_change', 'volume_spike'
    condition_value NUMERIC(12, 4) NOT NULL,  -- Target price or threshold
    condition_operator VARCHAR(10) NOT NULL,  -- '>', '<', '>=', '<=', '=='
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active', 'triggered', 'expired', 'disabled'
    notification_method VARCHAR(50) DEFAULT 'email',  -- 'email', 'webhook', 'none'
    email VARCHAR(255) NOT NULL,  -- User who owns this alert
    message TEXT,  -- Optional custom message when alert triggers
    triggered_at TIMESTAMPTZ,  -- When the alert was triggered
    triggered_price NUMERIC(12, 4),  -- Price when alert triggered
    expires_at TIMESTAMPTZ,  -- Optional expiration date
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT valid_status CHECK (status IN ('active', 'triggered', 'expired', 'disabled')),
    CONSTRAINT valid_alert_type CHECK (alert_type IN ('price_above', 'price_below', 'percent_change', 'volume_spike'))
);

-- Index for efficient querying of active alerts by symbol
CREATE INDEX IF NOT EXISTS idx_price_alerts_symbol_status 
    ON price_alerts(symbol, status) 
    WHERE status = 'active';

-- Index for querying by user
CREATE INDEX IF NOT EXISTS idx_price_alerts_email 
    ON price_alerts(email);

-- Index for finding recently triggered alerts
CREATE INDEX IF NOT EXISTS idx_price_alerts_triggered_at 
    ON price_alerts(triggered_at DESC) 
    WHERE triggered_at IS NOT NULL;

-- Index for cleaning up expired alerts
CREATE INDEX IF NOT EXISTS idx_price_alerts_expires_at 
    ON price_alerts(expires_at) 
    WHERE expires_at IS NOT NULL AND status = 'active';

-- Comments for documentation
COMMENT ON TABLE price_alerts IS 'Price alert rules for automated notifications when conditions are met';
COMMENT ON COLUMN price_alerts.symbol IS 'Stock ticker symbol to monitor';
COMMENT ON COLUMN price_alerts.alert_type IS 'Type of alert: price_above, price_below, percent_change, volume_spike';
COMMENT ON COLUMN price_alerts.condition_value IS 'Threshold value (e.g., target price of $150.00, or percent change of 5.0)';
COMMENT ON COLUMN price_alerts.condition_operator IS 'Comparison operator: >, <, >=, <=, ==';
COMMENT ON COLUMN price_alerts.status IS 'Current state: active (monitoring), triggered (fired), expired, or disabled';
COMMENT ON COLUMN price_alerts.triggered_at IS 'Timestamp when the alert condition was first met';
COMMENT ON COLUMN price_alerts.triggered_price IS 'The price that triggered the alert (for reference)';
COMMENT ON COLUMN price_alerts.expires_at IS 'Optional expiration timestamp - alert auto-expires after this date';
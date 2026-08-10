-- Create user_activity table for tracking agent interactions and user actions
-- This table logs all significant user and agent actions for analytics and audit trails
-- Run this ONCE before using activity tracking

CREATE TABLE IF NOT EXISTS user_activity (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,  -- User who performed the action
    activity_type VARCHAR(50) NOT NULL,  -- 'agent_query', 'watchlist_add', 'watchlist_remove', 'research_note_save', 'alert_create', etc.
    symbol VARCHAR(10),  -- Related ticker symbol (if applicable)
    action_details JSONB,  -- Flexible field for action-specific data (query text, tool used, results summary)
    session_id VARCHAR(100),  -- Optional session identifier for grouping related actions
    ip_address INET,  -- Client IP address (for security/audit)
    user_agent TEXT,  -- Browser/client user agent
    response_time_ms INTEGER,  -- Time taken to process the action (for performance monitoring)
    success BOOLEAN NOT NULL DEFAULT true,  -- Whether the action succeeded
    error_message TEXT,  -- Error details if success=false
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT valid_activity_type CHECK (activity_type IN (
        'agent_query', 'vector_search', 'get_news', 'get_ticker_details',
        'watchlist_add', 'watchlist_remove', 'research_note_save',
        'alert_create', 'alert_trigger', 'price_check', 'login', 'logout'
    ))
);

-- Index for efficient querying by user and time range
CREATE INDEX IF NOT EXISTS idx_user_activity_email_time 
    ON user_activity(email, created_at DESC);

-- Index for querying by activity type
CREATE INDEX IF NOT EXISTS idx_user_activity_type 
    ON user_activity(activity_type, created_at DESC);

-- Index for querying by symbol (track which stocks get the most attention)
CREATE INDEX IF NOT EXISTS idx_user_activity_symbol 
    ON user_activity(symbol, created_at DESC) 
    WHERE symbol IS NOT NULL;

-- Index for finding errors
CREATE INDEX IF NOT EXISTS idx_user_activity_errors 
    ON user_activity(created_at DESC) 
    WHERE success = false;

-- Index for session-based analysis
CREATE INDEX IF NOT EXISTS idx_user_activity_session 
    ON user_activity(session_id, created_at) 
    WHERE session_id IS NOT NULL;

-- Partial index for performance monitoring (slow queries)
CREATE INDEX IF NOT EXISTS idx_user_activity_slow_queries 
    ON user_activity(response_time_ms DESC, created_at DESC) 
    WHERE response_time_ms > 1000;

-- Comments for documentation
COMMENT ON TABLE user_activity IS 'Audit trail and analytics log for all user and agent actions';
COMMENT ON COLUMN user_activity.email IS 'User who performed the action';
COMMENT ON COLUMN user_activity.activity_type IS 'Type of action: agent_query, watchlist_add, research_note_save, etc.';
COMMENT ON COLUMN user_activity.symbol IS 'Related stock ticker (if the action involved a specific stock)';
COMMENT ON COLUMN user_activity.action_details IS 'JSON field for action-specific context: query text, tool parameters, result summary';
COMMENT ON COLUMN user_activity.session_id IS 'Optional session identifier to group related actions in one user session';
COMMENT ON COLUMN user_activity.response_time_ms IS 'Milliseconds taken to complete the action (for performance monitoring)';
COMMENT ON COLUMN user_activity.success IS 'Whether the action completed successfully (false indicates an error)';
COMMENT ON COLUMN user_activity.error_message IS 'Error details when success=false (for debugging and alerting)';
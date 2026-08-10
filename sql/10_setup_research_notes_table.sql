-- Create research_notes table for agent-saved research insights
-- This table stores research notes created by the AI agent via the save_research_note MCP tool
-- Run this ONCE before using the agent's save_research_note functionality

CREATE TABLE IF NOT EXISTS research_notes (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    note_type VARCHAR(50) NOT NULL,  -- 'fundamental', 'technical', 'news', 'sentiment', etc.
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    sources JSONB,  -- Array of source URLs or references
    metadata JSONB,  -- Flexible field for additional context (sentiment scores, metrics, etc.)
    email VARCHAR(255) NOT NULL,  -- User who created/owns this note
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for efficient querying by symbol and user
CREATE INDEX IF NOT EXISTS idx_research_notes_symbol_email 
    ON research_notes(symbol, email);

-- Index for querying by note type
CREATE INDEX IF NOT EXISTS idx_research_notes_type 
    ON research_notes(note_type);

-- Index for time-based queries (most recent notes)
CREATE INDEX IF NOT EXISTS idx_research_notes_created_at 
    ON research_notes(created_at DESC);

-- Index for full-text search on title and content (if needed)
CREATE INDEX IF NOT EXISTS idx_research_notes_search 
    ON research_notes USING GIN(to_tsvector('english', title || ' ' || content));

-- Comments for documentation
COMMENT ON TABLE research_notes IS 'AI agent research insights and analysis notes for tracked stocks';
COMMENT ON COLUMN research_notes.symbol IS 'Stock ticker symbol this note relates to';
COMMENT ON COLUMN research_notes.note_type IS 'Category of research: fundamental, technical, news, sentiment, etc.';
COMMENT ON COLUMN research_notes.content IS 'Main research insight or analysis';
COMMENT ON COLUMN research_notes.sources IS 'JSON array of source URLs or citations used in this research';
COMMENT ON COLUMN research_notes.metadata IS 'Flexible JSON field for additional context like sentiment scores, metrics, confidence levels';
COMMENT ON COLUMN research_notes.email IS 'Email of the user who created this note (for multi-user support)';
-- Lakebase SQL Schema for Technical Indicator Embeddings
-- Purpose: Store vector embeddings of technical analysis narratives
--
-- This table stores embeddings of generated text summaries describing technical indicators
-- (RSI, SMA, EMA, MACD) for each ticker on each date. Enables semantic search for
-- technical patterns like "bullish golden cross" or "oversold with positive momentum"
--
-- Note: The embedding dimension (384) matches sentence-transformers/all-MiniLM-L6-v2

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create technical_indicator_embeddings table
CREATE TABLE IF NOT EXISTS technical_indicator_embeddings (
    id TEXT PRIMARY KEY,  -- SHA256 hash of (ticker || date)
    ticker TEXT NOT NULL,  -- Stock ticker symbol
    date DATE NOT NULL,  -- Date of the technical indicator snapshot
    embedding_text TEXT NOT NULL,  -- Generated narrative describing technical state
    embedding vector(384),  -- 384-dimensional vector from all-MiniLM-L6-v2
    model_name TEXT NOT NULL,  -- Model used for embedding
    embedded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- When embedding was computed
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- Last update timestamp
    UNIQUE(ticker, date)  -- One embedding per ticker per date
);

-- Create index for vector similarity search (cosine distance)
CREATE INDEX IF NOT EXISTS technical_indicator_embeddings_vector_idx 
    ON technical_indicator_embeddings 
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Create index for ticker lookups
CREATE INDEX IF NOT EXISTS technical_indicator_embeddings_ticker_idx 
    ON technical_indicator_embeddings(ticker);

-- Create index for date range queries
CREATE INDEX IF NOT EXISTS technical_indicator_embeddings_date_idx 
    ON technical_indicator_embeddings(date DESC);

-- Create composite index for ticker + date queries
CREATE INDEX IF NOT EXISTS technical_indicator_embeddings_ticker_date_idx 
    ON technical_indicator_embeddings(ticker, date DESC);

-- Add table and column comments
COMMENT ON TABLE technical_indicator_embeddings IS 'Vector embeddings of technical indicator narratives for pattern matching';
COMMENT ON COLUMN technical_indicator_embeddings.embedding_text IS 'Generated text describing RSI, SMA, EMA, MACD patterns';
COMMENT ON COLUMN technical_indicator_embeddings.embedding IS '384-dimensional sentence embedding from all-MiniLM-L6-v2';

-- Example similarity search query:
-- Find tickers with similar technical patterns to a query
--
-- SELECT 
--     ticker, 
--     date,
--     embedding_text, 
--     1 - (embedding <=> :query_embedding) AS similarity_score
-- FROM technical_indicator_embeddings
-- WHERE date >= CURRENT_DATE - INTERVAL '30 days'
-- ORDER BY embedding <=> :query_embedding
-- LIMIT 10;
--
-- Example query: "bullish golden cross with positive MACD momentum"

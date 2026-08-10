-- Lakebase SQL Schema for Price Pattern Embeddings
-- Purpose: Store vector embeddings of price movement narratives
--
-- This table stores embeddings of generated text summaries describing price patterns,
-- volume, trends, and trading ranges for each ticker on each date. Enables semantic
-- search for price behaviors like "strong uptrend with high volume" or "near 52-week high"
--
-- Note: The embedding dimension (384) matches sentence-transformers/all-MiniLM-L6-v2

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create price_pattern_embeddings table
CREATE TABLE IF NOT EXISTS price_pattern_embeddings (
    id TEXT PRIMARY KEY,  -- SHA256 hash of (symbol || date)
    symbol TEXT NOT NULL,  -- Stock ticker symbol
    date DATE NOT NULL,  -- Date of the price snapshot
    embedding_text TEXT NOT NULL,  -- Generated narrative describing price pattern
    embedding vector(384),  -- 384-dimensional vector from all-MiniLM-L6-v2
    model_name TEXT NOT NULL,  -- Model used for embedding
    close_price DECIMAL(10, 2),  -- Closing price (for filtering/sorting)
    volume BIGINT,  -- Trading volume (for filtering/sorting)
    embedded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- When embedding was computed
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- Last update timestamp
    UNIQUE(symbol, date)  -- One embedding per symbol per date
);

-- Create index for vector similarity search (cosine distance)
CREATE INDEX IF NOT EXISTS price_pattern_embeddings_vector_idx 
    ON price_pattern_embeddings 
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Create index for symbol lookups
CREATE INDEX IF NOT EXISTS price_pattern_embeddings_symbol_idx 
    ON price_pattern_embeddings(symbol);

-- Create index for date range queries
CREATE INDEX IF NOT EXISTS price_pattern_embeddings_date_idx 
    ON price_pattern_embeddings(date DESC);

-- Create composite index for symbol + date queries
CREATE INDEX IF NOT EXISTS price_pattern_embeddings_symbol_date_idx 
    ON price_pattern_embeddings(symbol, date DESC);

-- Create index for price filtering
CREATE INDEX IF NOT EXISTS price_pattern_embeddings_close_price_idx 
    ON price_pattern_embeddings(close_price);

-- Add table and column comments
COMMENT ON TABLE price_pattern_embeddings IS 'Vector embeddings of price pattern narratives for behavior matching';
COMMENT ON COLUMN price_pattern_embeddings.embedding_text IS 'Generated text describing price, volume, trends, and trading ranges';
COMMENT ON COLUMN price_pattern_embeddings.embedding IS '384-dimensional sentence embedding from all-MiniLM-L6-v2';
COMMENT ON COLUMN price_pattern_embeddings.close_price IS 'Closing price stored for filtering and sorting';
COMMENT ON COLUMN price_pattern_embeddings.volume IS 'Trading volume stored for filtering and sorting';

-- Example similarity search query:
-- Find stocks with similar price patterns to a query
--
-- SELECT 
--     symbol, 
--     date,
--     close_price,
--     volume,
--     embedding_text, 
--     1 - (embedding <=> :query_embedding) AS similarity_score
-- FROM price_pattern_embeddings
-- WHERE date >= CURRENT_DATE - INTERVAL '7 days'
--   AND volume > 1000000  -- Optional: filter by volume
-- ORDER BY embedding <=> :query_embedding
-- LIMIT 10;
--
-- Example query: "strong uptrend with increasing volume near 52-week high"

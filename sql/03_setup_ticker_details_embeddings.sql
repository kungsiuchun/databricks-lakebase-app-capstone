-- Lakebase SQL Schema for Ticker Details Embeddings
-- Purpose: Store vector embeddings of company descriptions from ticker_details table
--
-- Usage:
--   1. Run this script in your Lakebase Postgres database
--   2. The table will store embeddings of company descriptions
--   3. Use for semantic search: "Find companies working on AI chips"
--
-- Note: The embedding dimension (384) matches sentence-transformers/all-MiniLM-L6-v2

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create ticker_details_embeddings table
CREATE TABLE IF NOT EXISTS ticker_details_embeddings (
    id TEXT PRIMARY KEY,  -- SHA256 hash of symbol (for idempotency)
    symbol TEXT NOT NULL UNIQUE,  -- Stock ticker symbol
    name TEXT,  -- Company name
    embedding_text TEXT NOT NULL,  -- The text that was embedded (company description)
    embedding vector(384),  -- 384-dimensional vector from all-MiniLM-L6-v2
    model_name TEXT NOT NULL,  -- Model used for embedding (e.g., 'sentence-transformers/all-MiniLM-L6-v2')
    embedded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- When embedding was computed
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- Last update timestamp
);

-- Create index for vector similarity search (cosine distance)
-- The ivfflat index enables fast approximate nearest neighbor search
CREATE INDEX IF NOT EXISTS ticker_details_embeddings_vector_idx 
    ON ticker_details_embeddings 
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Create index for symbol lookups
CREATE INDEX IF NOT EXISTS ticker_details_embeddings_symbol_idx 
    ON ticker_details_embeddings(symbol);

-- Create index for timestamp queries
CREATE INDEX IF NOT EXISTS ticker_details_embeddings_embedded_at_idx 
    ON ticker_details_embeddings(embedded_at DESC);

-- Add table and column comments
COMMENT ON TABLE ticker_details_embeddings IS 'Vector embeddings of company descriptions for semantic search';
COMMENT ON COLUMN ticker_details_embeddings.id IS 'SHA256 hash of symbol for idempotency';
COMMENT ON COLUMN ticker_details_embeddings.embedding_text IS 'The raw company description text that was embedded';
COMMENT ON COLUMN ticker_details_embeddings.embedding IS '384-dimensional sentence embedding from all-MiniLM-L6-v2';

-- Example similarity search query:
-- Find companies similar to a query (replace :query_embedding with your embedded query text)
--
-- SELECT 
--     symbol, 
--     name, 
--     embedding_text, 
--     1 - (embedding <=> :query_embedding) AS similarity_score
-- FROM ticker_details_embeddings
-- ORDER BY embedding <=> :query_embedding
-- LIMIT 10;
--
-- Example: Find companies most similar to "NVIDIA"
-- 1. First embed the query "GPU chips for AI and data centers"
-- 2. Then run: ORDER BY embedding <=> '[0.123, 0.456, ...]'::vector

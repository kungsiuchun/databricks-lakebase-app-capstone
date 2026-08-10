-- Migration: Add industry columns to ticker_details table
-- Date: 2025-01-XX
-- Purpose: Store SIC code and industry description from Polygon API

ALTER TABLE ticker_details 
ADD COLUMN IF NOT EXISTS sic_code VARCHAR(10),
ADD COLUMN IF NOT EXISTS sic_description VARCHAR(255);

-- Create index for faster industry searches
CREATE INDEX IF NOT EXISTS idx_ticker_details_sic_description 
ON ticker_details (sic_description);

-- Verification query
SELECT 
    symbol, 
    name, 
    sic_code, 
    sic_description 
FROM ticker_details 
WHERE sic_description IS NOT NULL 
LIMIT 5;

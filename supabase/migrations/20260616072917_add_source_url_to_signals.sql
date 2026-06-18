-- Add source_url column for tracking original URL
ALTER TABLE signals ADD COLUMN source_url TEXT;

-- Create index for deduplication
CREATE INDEX idx_signals_source_url ON signals(source_url);
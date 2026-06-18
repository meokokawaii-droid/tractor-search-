-- Add status column for quick action tracking
ALTER TABLE signals ADD COLUMN status TEXT DEFAULT 'new' CHECK (status IN ('new', 'following', 'invalid', 'done'));

-- Create index for status filtering
CREATE INDEX idx_signals_status ON signals(status);

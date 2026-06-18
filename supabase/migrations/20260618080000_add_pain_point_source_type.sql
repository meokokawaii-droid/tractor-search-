-- Add pain_point and source_type columns to signals table
ALTER TABLE signals
  ADD COLUMN IF NOT EXISTS pain_point TEXT,
  ADD COLUMN IF NOT EXISTS source_type TEXT;

-- Add comment for documentation
COMMENT ON COLUMN signals.pain_point IS 'Detected pain point: Leaking, Worn out, Broken, Rusted, Overheating, Noise, Stuck, Not starting, Slipping, Vibration';
COMMENT ON COLUMN signals.source_type IS 'Source type: forum, youtube, news, general_web';

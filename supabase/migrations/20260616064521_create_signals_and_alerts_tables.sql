-- Signals table for storing extracted demand signals
CREATE TABLE signals (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  raw_content TEXT NOT NULL,
  location TEXT,
  region TEXT, -- 'Africa', 'Southeast Asia', etc.
  vehicle_model TEXT,
  part_category TEXT,
  urgency TEXT CHECK (urgency IN ('high_demand', 'inquiry')),
  source TEXT,
  source_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  processed_at TIMESTAMPTZ
);

-- Alerts table for urgent stock recommendations
CREATE TABLE alerts (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  part_category TEXT NOT NULL,
  vehicle_model TEXT,
  match_count INTEGER NOT NULL,
  signal_ids UUID[] NOT NULL,
  message TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;

-- RLS policies for signals (public read for dashboard, authenticated write)
CREATE POLICY "select_signals" ON signals FOR SELECT TO authenticated USING (true);
CREATE POLICY "insert_signals" ON signals FOR INSERT TO authenticated WITH CHECK (true);

-- RLS policies for alerts
CREATE POLICY "select_alerts" ON alerts FOR SELECT TO authenticated USING (true);
CREATE POLICY "insert_alerts" ON alerts FOR INSERT TO authenticated WITH CHECK (true);

-- Index for efficient queries
CREATE INDEX idx_signals_region ON signals(region);
CREATE INDEX idx_signals_part_category ON signals(part_category);
CREATE INDEX idx_signals_created_at ON signals(created_at DESC);
CREATE INDEX idx_alerts_active ON alerts(is_active);

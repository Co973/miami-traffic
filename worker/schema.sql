CREATE TABLE IF NOT EXISTS community_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  submission_id TEXT NOT NULL,
  month TEXT NOT NULL,
  window TEXT NOT NULL,
  duration_seconds INTEGER NOT NULL,
  observation_count INTEGER NOT NULL,
  points_json TEXT NOT NULL,
  received_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_community_runs_submission ON community_runs(submission_id);
CREATE INDEX IF NOT EXISTS idx_community_runs_window ON community_runs(window, month);

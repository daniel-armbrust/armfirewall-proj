PRAGMA foreign_keys = ON;

-- Stores daemon log messages emitted by HomeFirewall processes.
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    level TEXT NOT NULL CHECK (level IN ('INFO', 'WARNING', 'ERROR', 'FATAL')),
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Speeds up log lookup by daemon and date.
CREATE INDEX IF NOT EXISTS idx_logs_source_created_at
ON logs (source, created_at);

-- Speeds up log lookup by severity and date.
CREATE INDEX IF NOT EXISTS idx_logs_level_created_at
ON logs (level, created_at);

PRAGMA foreign_keys = ON;

-- Stores ICMP latency monitoring targets executed through ping.
CREATE TABLE IF NOT EXISTS latency_targets (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface TEXT NOT NULL,
     target TEXT NOT NULL,
     count INTEGER NOT NULL DEFAULT 3 CHECK (count > 0),
     timeout INTEGER NOT NULL DEFAULT 3 CHECK (timeout > 0),
     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     UNIQUE (iface, target)
);

-- Speeds up lookup of latency targets by interface.
CREATE INDEX IF NOT EXISTS idx_latency_targets_iface
ON latency_targets (iface);

-- Speeds up lookup of latency targets by destination.
CREATE INDEX IF NOT EXISTS idx_latency_targets_target
ON latency_targets (target);

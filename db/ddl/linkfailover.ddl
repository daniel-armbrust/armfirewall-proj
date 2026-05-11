PRAGMA foreign_keys = ON;

-- Stores global Link Failover daemon settings.
CREATE TABLE IF NOT EXISTS linkfailover_settings (
     id INTEGER PRIMARY KEY CHECK (id = 1),
     target TEXT NOT NULL DEFAULT 'registro.br',
     timeout_seconds INTEGER NOT NULL DEFAULT 3 CHECK (timeout_seconds BETWEEN 1 AND 60),
     attempts INTEGER NOT NULL DEFAULT 3 CHECK (attempts BETWEEN 1 AND 20),
     interval_seconds INTEGER NOT NULL DEFAULT 1 CHECK (interval_seconds BETWEEN 0 AND 3600),
     max_latency_ms REAL CHECK (max_latency_ms IS NULL OR max_latency_ms >= 0),
     check_interval_seconds INTEGER NOT NULL DEFAULT 10 CHECK (check_interval_seconds BETWEEN 1 AND 86400),
     current_iface TEXT,
     last_route_change_at TEXT,
     last_checked_at TEXT,
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO linkfailover_settings (
     id, target, timeout_seconds, attempts, interval_seconds, check_interval_seconds
)
VALUES (1, 'registro.br', 3, 3, 1, 10);

-- Stores each monitored uplink participating in Link Failover.
CREATE TABLE IF NOT EXISTS linkfailover_links (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface TEXT NOT NULL,
     priority INTEGER NOT NULL DEFAULT 100 CHECK (priority BETWEEN 1 AND 999),
     status TEXT NOT NULL DEFAULT 'unknown' CHECK (status IN ('unknown', 'healthy', 'failed')),
     last_latency_ms REAL,
     last_error TEXT,
     last_checked_at TEXT,
     success_count INTEGER NOT NULL DEFAULT 0 CHECK (success_count >= 0),
     fail_count INTEGER NOT NULL DEFAULT 0 CHECK (fail_count >= 0),
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     UNIQUE (iface)
);

CREATE INDEX IF NOT EXISTS idx_linkfailover_links_priority
ON linkfailover_links (priority, iface);

-- Stores daemon decisions and route-change history.
CREATE TABLE IF NOT EXISTS linkfailover_events (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     link_id INTEGER,
     event_type TEXT NOT NULL CHECK (
          event_type IN (
               'check',
               'config',
               'route_change',
               'warning',
               'error'
          )
     ),
     message TEXT NOT NULL,
     details_json TEXT,
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (link_id) REFERENCES linkfailover_links(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_linkfailover_events_created
ON linkfailover_events (created_at);

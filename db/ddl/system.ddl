-- Stores the current operating-system snapshot collected by collectord.
CREATE TABLE IF NOT EXISTS system_snapshot (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    hostname TEXT NOT NULL,
    cpu_model TEXT NOT NULL,
    cpu_count INTEGER NOT NULL CHECK (cpu_count >= 0),
    cpu_usage_percent REAL NOT NULL CHECK (cpu_usage_percent BETWEEN 0 AND 100),
    architecture TEXT NOT NULL,
    platform TEXT NOT NULL,
    os_name TEXT NOT NULL,
    memory_total_bytes INTEGER NOT NULL CHECK (memory_total_bytes >= 0),
    memory_used_bytes INTEGER NOT NULL CHECK (memory_used_bytes >= 0),
    memory_available_bytes INTEGER NOT NULL CHECK (memory_available_bytes >= 0),
    process_count INTEGER NOT NULL CHECK (process_count >= 0),
    root_disk_total_bytes INTEGER NOT NULL CHECK (root_disk_total_bytes >= 0),
    root_disk_used_bytes INTEGER NOT NULL CHECK (root_disk_used_bytes >= 0),
    root_disk_free_bytes INTEGER NOT NULL CHECK (root_disk_free_bytes >= 0),
    collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

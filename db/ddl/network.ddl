-- Stores metadata for the current kernel neighbor-cache snapshot.
CREATE TABLE IF NOT EXISTS neighbor_snapshot (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    source TEXT NOT NULL DEFAULT 'ip-neighbor',
    collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Stores neighbor entries returned by ip neighbor show for the current snapshot.
CREATE TABLE IF NOT EXISTS neighbor_entry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL DEFAULT 1,
    addr_family TEXT NOT NULL CHECK (addr_family IN ('ipv4', 'ipv6')),
    ip_address TEXT NOT NULL,
    mac_address TEXT,
    iface_name TEXT,
    state TEXT NOT NULL,
    flags TEXT,
    raw_entry TEXT NOT NULL,
    collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (snapshot_id) REFERENCES neighbor_snapshot(id) ON DELETE CASCADE,
    UNIQUE (snapshot_id, addr_family, iface_name, ip_address)
);

CREATE INDEX IF NOT EXISTS idx_neighbor_entry_interface
ON neighbor_entry (iface_name);

CREATE INDEX IF NOT EXISTS idx_neighbor_entry_state
ON neighbor_entry (state);

PRAGMA foreign_keys = ON;

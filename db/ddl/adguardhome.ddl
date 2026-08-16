PRAGMA foreign_keys = ON;

-- Stores the singleton AdGuard Home configuration managed by ArmFirewall.
CREATE TABLE IF NOT EXISTS adguardhome_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    dns_bind_host TEXT NOT NULL DEFAULT '127.0.0.1',
    dns_port INTEGER NOT NULL DEFAULT 5353 CHECK (dns_port BETWEEN 1 AND 65535),
    web_bind_host TEXT NOT NULL DEFAULT '127.0.0.1',
    web_port INTEGER NOT NULL DEFAULT 3001 CHECK (web_port BETWEEN 1 AND 65535),
    protection_enabled INTEGER NOT NULL DEFAULT 1 CHECK (protection_enabled IN (0, 1)),
    filtering_enabled INTEGER NOT NULL DEFAULT 1 CHECK (filtering_enabled IN (0, 1)),
    safe_browsing_enabled INTEGER NOT NULL DEFAULT 0 CHECK (safe_browsing_enabled IN (0, 1)),
    parental_enabled INTEGER NOT NULL DEFAULT 0 CHECK (parental_enabled IN (0, 1)),
    safe_search_enabled INTEGER NOT NULL DEFAULT 0 CHECK (safe_search_enabled IN (0, 1)),
    upstream_dns_servers_json TEXT NOT NULL DEFAULT '["https://dns.cloudflare.com/dns-query"]',
    fallback_dns_servers_json TEXT NOT NULL DEFAULT '[]',
    bootstrap_dns_servers_json TEXT NOT NULL DEFAULT '["1.1.1.1","8.8.8.8"]',
    filter_update_interval_hours INTEGER NOT NULL DEFAULT 24 CHECK (filter_update_interval_hours BETWEEN 1 AND 720),
    query_log_enabled INTEGER NOT NULL DEFAULT 1 CHECK (query_log_enabled IN (0, 1)),
    query_log_retention_hours INTEGER NOT NULL DEFAULT 2160 CHECK (query_log_retention_hours BETWEEN 1 AND 8760),
    statistics_interval_hours INTEGER NOT NULL DEFAULT 24 CHECK (statistics_interval_hours BETWEEN 1 AND 720),
    pending_apply INTEGER NOT NULL DEFAULT 0 CHECK (pending_apply IN (0, 1)),
    last_work_request_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO adguardhome_settings (id)
VALUES (1);

-- Stores remote block and allow filter sources synchronized by AdGuard Home.
CREATE TABLE IF NOT EXISTS adguardhome_filters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_url TEXT NOT NULL UNIQUE,
    filter_kind TEXT NOT NULL DEFAULT 'block' CHECK (filter_kind IN ('block', 'allow')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    last_updated_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Stores local domain rules configured from the ArmFirewall GUI.
CREATE TABLE IF NOT EXISTS adguardhome_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule TEXT NOT NULL UNIQUE,
    action TEXT NOT NULL CHECK (action IN ('allow', 'block')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'gui' CHECK (source IN ('gui', 'seed', 'import')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Stores DNS rewrites, such as an internal domain pointing to a LAN address.
CREATE TABLE IF NOT EXISTS adguardhome_rewrites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    answer TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (domain, answer)
);

CREATE INDEX IF NOT EXISTS idx_adguardhome_filters_enabled
ON adguardhome_filters (enabled, filter_kind);

CREATE INDEX IF NOT EXISTS idx_adguardhome_rules_enabled
ON adguardhome_rules (enabled, action);

CREATE INDEX IF NOT EXISTS idx_adguardhome_rewrites_enabled
ON adguardhome_rewrites (enabled, domain);

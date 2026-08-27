PRAGMA foreign_keys = ON;

-- Stores global Dnsmasq configuration metadata managed by ArmFirewall.
CREATE TABLE IF NOT EXISTS dnsmasq_settings (
     id INTEGER PRIMARY KEY CHECK (id = 1),
     dns_enabled INTEGER NOT NULL DEFAULT 0 CHECK (dns_enabled IN (0, 1)),
     local_domain TEXT NOT NULL DEFAULT 'armfirewall.local',
     upstream_dns_servers_json TEXT NOT NULL DEFAULT '["8.8.8.8","1.1.1.1"]',
     adguardhome_upstream_enabled INTEGER NOT NULL DEFAULT 0 CHECK (adguardhome_upstream_enabled IN (0, 1)),
     cache_size INTEGER NOT NULL DEFAULT 1000 CHECK (cache_size BETWEEN 0 AND 1000000),
     expand_hosts INTEGER NOT NULL DEFAULT 1 CHECK (expand_hosts IN (0, 1)),
     domain_needed INTEGER NOT NULL DEFAULT 1 CHECK (domain_needed IN (0, 1)),
     bogus_priv INTEGER NOT NULL DEFAULT 1 CHECK (bogus_priv IN (0, 1)),
     extra_options TEXT NOT NULL DEFAULT '',
     pending_apply INTEGER NOT NULL DEFAULT 0 CHECK (pending_apply IN (0, 1)),
     last_work_request_id INTEGER,
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO dnsmasq_settings (id)
VALUES (1);

-- Stores DNS and DHCP settings scoped to one interface or to the global scope.
CREATE TABLE IF NOT EXISTS dnsmasq_interface_configs (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface TEXT NOT NULL UNIQUE,
     dns_enabled INTEGER NOT NULL DEFAULT 0 CHECK (dns_enabled IN (0, 1)),
     local_domain TEXT NOT NULL DEFAULT 'armfirewall.local',
     upstream_dns_servers_json TEXT NOT NULL DEFAULT '["8.8.8.8","1.1.1.1"]',
     adguardhome_upstream_enabled INTEGER NOT NULL DEFAULT 0 CHECK (adguardhome_upstream_enabled IN (0, 1)),
     cache_size INTEGER NOT NULL DEFAULT 1000 CHECK (cache_size BETWEEN 0 AND 1000000),
     expand_hosts INTEGER NOT NULL DEFAULT 1 CHECK (expand_hosts IN (0, 1)),
     domain_needed INTEGER NOT NULL DEFAULT 1 CHECK (domain_needed IN (0, 1)),
     bogus_priv INTEGER NOT NULL DEFAULT 1 CHECK (bogus_priv IN (0, 1)),
     dhcp_enabled INTEGER NOT NULL DEFAULT 0 CHECK (dhcp_enabled IN (0, 1)),
     dhcp_range_start TEXT NOT NULL DEFAULT '',
     dhcp_range_end TEXT NOT NULL DEFAULT '',
     lease_time TEXT NOT NULL DEFAULT '12h',
     dhcp_authoritative INTEGER NOT NULL DEFAULT 0 CHECK (dhcp_authoritative IN (0, 1)),
     ipv6_ra_enabled INTEGER NOT NULL DEFAULT 0 CHECK (ipv6_ra_enabled IN (0, 1)),
     ipv6_ra_names INTEGER NOT NULL DEFAULT 1 CHECK (ipv6_ra_names IN (0, 1)),
     ipv6_ra_lifetime TEXT NOT NULL DEFAULT '4h',
     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Stores domain-specific upstream DNS forwarders for one interface configuration.
CREATE TABLE IF NOT EXISTS dnsmasq_domain_upstreams (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     interface_config_id INTEGER NOT NULL,
     domain TEXT NOT NULL,
     upstream_dns_servers_json TEXT NOT NULL,
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     UNIQUE (interface_config_id, domain),
     FOREIGN KEY (interface_config_id) REFERENCES dnsmasq_interface_configs(id) ON DELETE CASCADE
);

-- Stores global domain-specific upstream DNS forwarders.
CREATE TABLE IF NOT EXISTS dnsmasq_global_domain_upstreams (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     domain TEXT NOT NULL UNIQUE,
     upstream_dns_servers_json TEXT NOT NULL,
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dnsmasq_interface_configs_enabled
ON dnsmasq_interface_configs (enabled, iface);

CREATE INDEX IF NOT EXISTS idx_dnsmasq_domain_upstreams_interface
ON dnsmasq_domain_upstreams (interface_config_id, domain);

CREATE INDEX IF NOT EXISTS idx_dnsmasq_global_domain_upstreams_domain
ON dnsmasq_global_domain_upstreams (domain);

-- Stores persistent IPv4 DHCP reservations managed by ArmFirewall.
CREATE TABLE IF NOT EXISTS dnsmasq_static_leases (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     mac_address TEXT NOT NULL UNIQUE,
     ip_address TEXT NOT NULL UNIQUE,
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

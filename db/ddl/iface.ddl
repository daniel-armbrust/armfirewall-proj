---
--- Tabela para armazenar as interfaces de rede disponíveis no sistema operacional.
---
CREATE TABLE IF NOT EXISTS ifaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    is_actived INTEGER NOT NULL DEFAULT 0 CHECK (is_actived IN (0, 1)),
    description TEXT NOT NULL,
    mtu INTEGER,
    mac_address TEXT,
    role TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (role IN ('LAN', 'WAN', 'UNKNOWN')),
    type TEXT NOT NULL DEFAULT 'Ethernet',
    speed_mbps INTEGER NOT NULL DEFAULT 0,
    duplex TEXT NOT NULL DEFAULT 'unknown' CHECK (duplex IN ('full-duplex', 'half-duplex', 'unknown')),
    protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
    collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

---
--- Tabela para armazenar endereços IPv4 e IPv6 de uma interface de rede.
---
CREATE TABLE IF NOT EXISTS addresses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    iface_id INTEGER NOT NULL,
    addr_family TEXT NOT NULL CHECK (addr_family IN ('ipv4', 'ipv6')),
    addr TEXT NOT NULL,
    prefixlen TEXT NOT NULL,
    broadcast TEXT,
    scopeid TEXT,
    is_secondary INTEGER NOT NULL DEFAULT 0 CHECK (is_secondary IN (0, 1)),
    iface_name_secondary TEXT DEFAULT NULL,
    FOREIGN KEY (iface_id) REFERENCES ifaces(id)
);

---
--- Tabela para armazenar as estatísticas das interfaces de rede disponíveis no sistema operacional.
---
CREATE TABLE IF NOT EXISTS stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    iface_id INTEGER NOT NULL,
    rx_bytes INTEGER NOT NULL DEFAULT 0,
    rx_packets INTEGER NOT NULL DEFAULT 0,
    rx_errors INTEGER NOT NULL DEFAULT 0,
    rx_dropped INTEGER NOT NULL DEFAULT 0,
    rx_fifo INTEGER NOT NULL DEFAULT 0,
    rx_frame INTEGER NOT NULL DEFAULT 0,
    rx_multicast INTEGER NOT NULL DEFAULT 0,
    tx_bytes INTEGER NOT NULL DEFAULT 0,
    tx_packets INTEGER NOT NULL DEFAULT 0,
    tx_errors INTEGER NOT NULL DEFAULT 0,
    tx_dropped INTEGER NOT NULL DEFAULT 0,
    tx_fifo INTEGER NOT NULL DEFAULT 0,
    tx_collisions INTEGER NOT NULL DEFAULT 0,
    tx_carrier INTEGER NOT NULL DEFAULT 0,
    collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (iface_id) REFERENCES ifaces(id),
    UNIQUE (iface_id)
);

---
--- Tabela para armazenar os valores que serão aplicados no /proc de uma interface de rede.
--- 
CREATE TABLE IF NOT EXISTS proc (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    iface_id INTEGER NOT NULL,
    addr_family TEXT NOT NULL CHECK (addr_family IN ('ipv4', 'ipv6')),
    proc_path TEXT NOT NULL,
    description TEXT NOT NULL,
    default_value TEXT,
    desired_value TEXT,
    collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (iface_id) REFERENCES ifaces(id),
    UNIQUE (iface_id, addr_family, proc_path)
);

CREATE INDEX IF NOT EXISTS idx_proc_iface_id ON proc (iface_id);
CREATE INDEX IF NOT EXISTS idx_proc_addr_family ON proc (addr_family);
CREATE INDEX IF NOT EXISTS idx_proc_iface_family ON proc (iface_id, addr_family);

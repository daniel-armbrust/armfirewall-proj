PRAGMA foreign_keys = ON;

-- Stores the supported IPv6 transport protocols used by firewall rules.
CREATE TABLE IF NOT EXISTS protocols (
     name TEXT PRIMARY KEY CHECK (name IN ('all', 'tcp', 'udp', 'icmpv6')),
     description TEXT NOT NULL
);

INSERT OR IGNORE INTO protocols (name, description) VALUES
     ('all', 'All protocols'),
     ('tcp', 'Transmission Control Protocol'),
     ('udp', 'User Datagram Protocol'),
     ('icmpv6', 'Internet Control Message Protocol for IPv6');

-- Stores IPv6 NAT table PREROUTING rules applied before route lookup.
CREATE TABLE IF NOT EXISTS nat_prerouting_rules (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface_in TEXT,
     rule_order INTEGER NOT NULL,

     src_addr TEXT NOT NULL,
     src_port INTEGER,
     dst_addr TEXT NOT NULL,
     dst_port INTEGER,

     protocol_name TEXT NOT NULL,
     protocol_type INTEGER,
     protocol_code INTEGER,

     nat_action TEXT NOT NULL CHECK (nat_action IN ('DNAT', 'REDIRECT', 'ACCEPT', 'RETURN')),
     to_addr TEXT,
     to_port INTEGER,

     protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
     rule_source TEXT NOT NULL DEFAULT 'system' CHECK (rule_source IN ('system', 'user')),
     enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
     pending_delete INTEGER NOT NULL DEFAULT 0 CHECK (pending_delete IN (0, 1)),

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (protocol_name) REFERENCES protocols(name),
     CHECK (
          (
               protocol_name IN ('tcp', 'udp')
               AND protocol_type IS NULL
               AND protocol_code IS NULL
          )
          OR
          (
               protocol_name = 'all'
               AND src_port IS NULL
               AND dst_port IS NULL
               AND protocol_type IS NULL
               AND protocol_code IS NULL
          )
          OR
          (
               protocol_name = 'icmpv6'
               AND src_port IS NULL
               AND dst_port IS NULL
          )
     ),
     CHECK (
          (protocol_type IS NULL AND protocol_code IS NULL)
          OR
          (protocol_type IS NOT NULL AND protocol_code IS NOT NULL)
     )
);

-- Stores IPv6 NAT table INPUT rules for packets delivered to local sockets.
CREATE TABLE IF NOT EXISTS nat_input_rules (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface_in TEXT,
     rule_order INTEGER NOT NULL,

     src_addr TEXT NOT NULL,
     src_port INTEGER,
     dst_addr TEXT NOT NULL,
     dst_port INTEGER,

     protocol_name TEXT NOT NULL,
     protocol_type INTEGER,
     protocol_code INTEGER,

     nat_action TEXT NOT NULL CHECK (nat_action IN ('DNAT', 'REDIRECT', 'ACCEPT', 'RETURN')),
     to_addr TEXT,
     to_port INTEGER,

     protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
     rule_source TEXT NOT NULL DEFAULT 'system' CHECK (rule_source IN ('system', 'user')),
     enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (protocol_name) REFERENCES protocols(name),
     CHECK (
          (
               protocol_name IN ('tcp', 'udp')
               AND protocol_type IS NULL
               AND protocol_code IS NULL
          )
          OR
          (
               protocol_name = 'all'
               AND src_port IS NULL
               AND dst_port IS NULL
               AND protocol_type IS NULL
               AND protocol_code IS NULL
          )
          OR
          (
               protocol_name = 'icmpv6'
               AND src_port IS NULL
               AND dst_port IS NULL
          )
     ),
     CHECK (
          (protocol_type IS NULL AND protocol_code IS NULL)
          OR
          (protocol_type IS NOT NULL AND protocol_code IS NOT NULL)
     )
);

-- Stores IPv6 NAT table OUTPUT rules for locally generated packets.
CREATE TABLE IF NOT EXISTS nat_output_rules (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface_out TEXT,
     rule_order INTEGER NOT NULL,

     src_addr TEXT NOT NULL,
     src_port INTEGER,
     dst_addr TEXT NOT NULL,
     dst_port INTEGER,

     protocol_name TEXT NOT NULL,
     protocol_type INTEGER,
     protocol_code INTEGER,

     nat_action TEXT NOT NULL CHECK (nat_action IN ('DNAT', 'REDIRECT', 'ACCEPT', 'RETURN')),
     to_addr TEXT,
     to_port INTEGER,

     protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
     rule_source TEXT NOT NULL DEFAULT 'system' CHECK (rule_source IN ('system', 'user')),
     enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (protocol_name) REFERENCES protocols(name),
     CHECK (
          (
               protocol_name IN ('tcp', 'udp')
               AND protocol_type IS NULL
               AND protocol_code IS NULL
          )
          OR
          (
               protocol_name = 'all'
               AND src_port IS NULL
               AND dst_port IS NULL
               AND protocol_type IS NULL
               AND protocol_code IS NULL
          )
          OR
          (
               protocol_name = 'icmpv6'
               AND src_port IS NULL
               AND dst_port IS NULL
          )
     ),
     CHECK (
          (protocol_type IS NULL AND protocol_code IS NULL)
          OR
          (protocol_type IS NOT NULL AND protocol_code IS NOT NULL)
     )
);

-- Stores IPv6 NAT table POSTROUTING rules applied after route lookup.
CREATE TABLE IF NOT EXISTS nat_postrouting_rules (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface_out TEXT,
     rule_order INTEGER NOT NULL,

     src_addr TEXT NOT NULL,
     src_port INTEGER,
     dst_addr TEXT NOT NULL,
     dst_port INTEGER,

     protocol_name TEXT NOT NULL,
     protocol_type INTEGER,
     protocol_code INTEGER,

     nat_action TEXT NOT NULL CHECK (nat_action IN ('SNAT', 'MASQUERADE', 'ACCEPT', 'RETURN')),
     to_addr TEXT,
     to_port INTEGER,

     protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
     rule_source TEXT NOT NULL DEFAULT 'system' CHECK (rule_source IN ('system', 'user')),
     enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (protocol_name) REFERENCES protocols(name),
     CHECK (
          (
               protocol_name IN ('tcp', 'udp')
               AND protocol_type IS NULL
               AND protocol_code IS NULL
          )
          OR
          (
               protocol_name = 'all'
               AND src_port IS NULL
               AND dst_port IS NULL
               AND protocol_type IS NULL
               AND protocol_code IS NULL
          )
          OR
          (
               protocol_name = 'icmpv6'
               AND src_port IS NULL
               AND dst_port IS NULL
          )
     ),
     CHECK (
          (protocol_type IS NULL AND protocol_code IS NULL)
          OR
          (protocol_type IS NOT NULL AND protocol_code IS NOT NULL)
     )
);


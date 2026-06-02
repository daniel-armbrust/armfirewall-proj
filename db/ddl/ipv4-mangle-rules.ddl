PRAGMA foreign_keys = ON;

-- Stores the supported Layer 4 protocols used by firewall rules.
CREATE TABLE IF NOT EXISTS protocols (
     name TEXT PRIMARY KEY CHECK (name IN ('all', 'tcp', 'udp', 'icmp')),
     description TEXT NOT NULL
);

INSERT OR IGNORE INTO protocols (name, description) VALUES
     ('all', 'All protocols'),
     ('tcp', 'Transmission Control Protocol'),
     ('udp', 'User Datagram Protocol'),
     ('icmp', 'Internet Control Message Protocol');

-- Stores IPv4 mangle table PREROUTING rules for early packet modification.
CREATE TABLE IF NOT EXISTS mangle_prerouting_rules (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface_in TEXT,
     rule_order INTEGER NOT NULL,

     -- Conntrack
     ct_new INTEGER NOT NULL DEFAULT 0 CHECK (ct_new IN (0, 1)),
     ct_established INTEGER NOT NULL DEFAULT 0 CHECK (ct_established IN (0, 1)),
     ct_related INTEGER NOT NULL DEFAULT 0 CHECK (ct_related IN (0, 1)),
     ct_invalid INTEGER NOT NULL DEFAULT 0 CHECK (ct_invalid IN (0, 1)),

     src_addr TEXT NOT NULL,
     src_port INTEGER,
     dst_addr TEXT NOT NULL,
     dst_port INTEGER,

     protocol_name TEXT NOT NULL,
     protocol_type INTEGER,
     protocol_code INTEGER,

     mangle_action TEXT NOT NULL CHECK (mangle_action IN ('MARK', 'CONNMARK', 'DSCP', 'TOS', 'TTL', 'ACCEPT', 'DROP', 'RETURN')),
     mark_value TEXT,
     dscp_value TEXT,
     tos_value TEXT,
     ttl_value TEXT,

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
               protocol_name = 'icmp'
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

-- Stores IPv4 mangle table INPUT rules for packets delivered to local sockets.
CREATE TABLE IF NOT EXISTS mangle_input_rules (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface_in TEXT,
     rule_order INTEGER NOT NULL,

     -- Conntrack
     ct_new INTEGER NOT NULL DEFAULT 0 CHECK (ct_new IN (0, 1)),
     ct_established INTEGER NOT NULL DEFAULT 0 CHECK (ct_established IN (0, 1)),
     ct_related INTEGER NOT NULL DEFAULT 0 CHECK (ct_related IN (0, 1)),
     ct_invalid INTEGER NOT NULL DEFAULT 0 CHECK (ct_invalid IN (0, 1)),

     src_addr TEXT NOT NULL,
     src_port INTEGER,
     dst_addr TEXT NOT NULL,
     dst_port INTEGER,

     protocol_name TEXT NOT NULL,
     protocol_type INTEGER,
     protocol_code INTEGER,

     mangle_action TEXT NOT NULL CHECK (mangle_action IN ('MARK', 'CONNMARK', 'DSCP', 'TOS', 'TTL', 'ACCEPT', 'DROP', 'RETURN')),
     mark_value TEXT,
     dscp_value TEXT,
     tos_value TEXT,
     ttl_value TEXT,

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
               protocol_name = 'icmp'
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

-- Stores IPv4 mangle table FORWARD rules for routed packets.
CREATE TABLE IF NOT EXISTS mangle_forward_rules (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface_in TEXT,
     iface_out TEXT,
     rule_order INTEGER NOT NULL,

     -- Conntrack
     ct_new INTEGER NOT NULL DEFAULT 0 CHECK (ct_new IN (0, 1)),
     ct_established INTEGER NOT NULL DEFAULT 0 CHECK (ct_established IN (0, 1)),
     ct_related INTEGER NOT NULL DEFAULT 0 CHECK (ct_related IN (0, 1)),
     ct_invalid INTEGER NOT NULL DEFAULT 0 CHECK (ct_invalid IN (0, 1)),

     src_addr TEXT NOT NULL,
     src_port INTEGER,
     dst_addr TEXT NOT NULL,
     dst_port INTEGER,

     protocol_name TEXT NOT NULL,
     protocol_type INTEGER,
     protocol_code INTEGER,

     mangle_action TEXT NOT NULL CHECK (mangle_action IN ('MARK', 'CONNMARK', 'DSCP', 'TOS', 'TTL', 'ACCEPT', 'DROP', 'RETURN')),
     mark_value TEXT,
     dscp_value TEXT,
     tos_value TEXT,
     ttl_value TEXT,

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
               protocol_name = 'icmp'
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

-- Stores IPv4 mangle table OUTPUT rules for locally generated packets.
CREATE TABLE IF NOT EXISTS mangle_output_rules (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface_out TEXT,
     rule_order INTEGER NOT NULL,

     -- Conntrack
     ct_new INTEGER NOT NULL DEFAULT 0 CHECK (ct_new IN (0, 1)),
     ct_established INTEGER NOT NULL DEFAULT 0 CHECK (ct_established IN (0, 1)),
     ct_related INTEGER NOT NULL DEFAULT 0 CHECK (ct_related IN (0, 1)),
     ct_invalid INTEGER NOT NULL DEFAULT 0 CHECK (ct_invalid IN (0, 1)),

     src_addr TEXT NOT NULL,
     src_port INTEGER,
     dst_addr TEXT NOT NULL,
     dst_port INTEGER,

     protocol_name TEXT NOT NULL,
     protocol_type INTEGER,
     protocol_code INTEGER,

     mangle_action TEXT NOT NULL CHECK (mangle_action IN ('MARK', 'CONNMARK', 'DSCP', 'TOS', 'TTL', 'ACCEPT', 'DROP', 'RETURN')),
     mark_value TEXT,
     dscp_value TEXT,
     tos_value TEXT,
     ttl_value TEXT,

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
               protocol_name = 'icmp'
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

-- Stores IPv4 mangle table POSTROUTING rules for final packet modification.
CREATE TABLE IF NOT EXISTS mangle_postrouting_rules (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface_out TEXT,
     rule_order INTEGER NOT NULL,

     -- Conntrack
     ct_new INTEGER NOT NULL DEFAULT 0 CHECK (ct_new IN (0, 1)),
     ct_established INTEGER NOT NULL DEFAULT 0 CHECK (ct_established IN (0, 1)),
     ct_related INTEGER NOT NULL DEFAULT 0 CHECK (ct_related IN (0, 1)),
     ct_invalid INTEGER NOT NULL DEFAULT 0 CHECK (ct_invalid IN (0, 1)),

     src_addr TEXT NOT NULL,
     src_port INTEGER,
     dst_addr TEXT NOT NULL,
     dst_port INTEGER,

     protocol_name TEXT NOT NULL,
     protocol_type INTEGER,
     protocol_code INTEGER,

     mangle_action TEXT NOT NULL CHECK (mangle_action IN ('MARK', 'CONNMARK', 'DSCP', 'TOS', 'TTL', 'ACCEPT', 'DROP', 'RETURN')),
     mark_value TEXT,
     dscp_value TEXT,
     tos_value TEXT,
     ttl_value TEXT,

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
               protocol_name = 'icmp'
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

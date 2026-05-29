PRAGMA foreign_keys = ON;

-- Stores the supported IPv6 transport protocols used by firewall rules.
CREATE TABLE IF NOT EXISTS protocols (
     name TEXT PRIMARY KEY CHECK (name IN ('all', 'tcp', 'udp', 'icmpv6', 'esp')),
     description TEXT NOT NULL
);

INSERT OR IGNORE INTO protocols (name, description) VALUES
     ('all', 'All protocols'),
     ('tcp', 'Transmission Control Protocol'),
     ('udp', 'User Datagram Protocol'),
     ('icmpv6', 'Internet Control Message Protocol for IPv6'),
     ('esp', 'Encapsulating Security Payload');

-- Stores IPv6 filter table built-in chain policies.
CREATE TABLE IF NOT EXISTS filter_chain_policies (
     chain_name TEXT PRIMARY KEY CHECK (chain_name IN ('INPUT', 'FORWARD', 'OUTPUT')),
     policy TEXT NOT NULL DEFAULT 'DROP' CHECK (policy IN ('ACCEPT', 'DROP')),
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO filter_chain_policies (chain_name, policy) VALUES
     ('INPUT', 'DROP'),
     ('FORWARD', 'DROP'),
     ('OUTPUT', 'ACCEPT');

-- Stores IPv6 filter table rules for packets entering the firewall host.
CREATE TABLE IF NOT EXISTS filter_input_rules (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface_in TEXT NOT NULL,
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

     action TEXT NOT NULL DEFAULT 'DROP' CHECK (action IN ('DROP', 'REJECT', 'ACCEPT')),
     protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
     enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (protocol_name) REFERENCES protocols(name),
     CHECK (
          (
               protocol_name IN ('tcp', 'udp')
               AND src_port IS NOT NULL
               AND dst_port IS NOT NULL
               AND protocol_type IS NULL
               AND protocol_code IS NULL
          )
          OR
          (
               protocol_name IN ('all', 'esp')
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

-- Stores IPv6 filter table rules for packets forwarded through the firewall host.
CREATE TABLE IF NOT EXISTS filter_forward_rules (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface_in TEXT NOT NULL,
     iface_out TEXT NOT NULL,
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

     action TEXT NOT NULL DEFAULT 'DROP' CHECK (action IN ('DROP', 'REJECT', 'ACCEPT')),
     protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
     enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (protocol_name) REFERENCES protocols(name),
     CHECK (
          (
               protocol_name IN ('tcp', 'udp')
               AND src_port IS NOT NULL
               AND dst_port IS NOT NULL
               AND protocol_type IS NULL
               AND protocol_code IS NULL
          )
          OR
          (
               protocol_name IN ('all', 'esp')
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

-- Stores IPv6 filter table rules for packets generated by the firewall host.
CREATE TABLE IF NOT EXISTS filter_output_rules (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface_out TEXT NOT NULL,
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

     action TEXT NOT NULL DEFAULT 'DROP' CHECK (action IN ('DROP', 'REJECT', 'ACCEPT')),
     protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
     enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (protocol_name) REFERENCES protocols(name),
     CHECK (
          (
               protocol_name IN ('tcp', 'udp')
               AND src_port IS NOT NULL
               AND dst_port IS NOT NULL
               AND protocol_type IS NULL
               AND protocol_code IS NULL
          )
          OR
          (
               protocol_name IN ('all', 'esp')
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

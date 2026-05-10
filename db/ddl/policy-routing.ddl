PRAGMA foreign_keys = ON;

-- Stores Linux policy routing table names and numeric identifiers used by iproute2.
CREATE TABLE IF NOT EXISTS routing_tables (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     table_id INTEGER NOT NULL UNIQUE CHECK (table_id BETWEEN 1 AND 4294967295),
     table_name TEXT NOT NULL UNIQUE,
     description TEXT,

     protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     applied INTEGER NOT NULL DEFAULT 0 CHECK (applied IN (0, 1)),
     pending_delete INTEGER NOT NULL DEFAULT 0 CHECK (pending_delete IN (0, 1)),

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO routing_tables (table_id, table_name, description, protected, enabled, applied) VALUES
     (255, 'local', 'Reserved local routing table maintained by the kernel.', 1, 1, 1),
     (254, 'main', 'Default main routing table.', 1, 1, 1),
     (253, 'default', 'Reserved default routing table.', 1, 1, 1);

-- Stores routes that map to the Linux "ip route" command.
CREATE TABLE IF NOT EXISTS routes (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     route_order INTEGER NOT NULL DEFAULT 0,

     addr_family TEXT NOT NULL CHECK (addr_family IN ('ipv4', 'ipv6')),
     table_id INTEGER NOT NULL,

     route_type TEXT NOT NULL DEFAULT 'unicast' CHECK (
          route_type IN (
               'unicast',
               'local',
               'broadcast',
               'multicast',
               'throw',
               'unreachable',
               'prohibit',
               'blackhole',
               'anycast'
          )
     ),

     destination TEXT NOT NULL DEFAULT 'default',
     tos TEXT,

     gateway TEXT,
     dev TEXT,
     preferred_source TEXT,
     metric INTEGER CHECK (metric IS NULL OR metric >= 0),

     scope TEXT CHECK (
          scope IS NULL OR scope IN (
               'global',
               'site',
               'link',
               'host',
               'nowhere'
          )
     ),
     protocol TEXT CHECK (
          protocol IS NULL OR protocol IN (
               'redirect',
               'kernel',
               'boot',
               'static',
               'ra',
               'dhcp',
               'mrouted',
               'babel',
               'bird',
               'bootp',
               'dhcpv6',
               'dnrouted',
               'eigrp',
               'gated',
               'isis',
               'keepalived',
               'mrt',
               'ntk',
               'ospf',
               'ra',
               'rip',
               'static',
               'unspec',
               'xorp',
               'zebra'
          )
     ),

     mtu INTEGER CHECK (mtu IS NULL OR mtu > 0),
     advmss INTEGER CHECK (advmss IS NULL OR advmss > 0),
     initcwnd INTEGER CHECK (initcwnd IS NULL OR initcwnd >= 0),
     initrwnd INTEGER CHECK (initrwnd IS NULL OR initrwnd >= 0),
     rto_min TEXT,
     quickack INTEGER CHECK (quickack IS NULL OR quickack IN (0, 1)),
     congctl TEXT,

     onlink INTEGER NOT NULL DEFAULT 0 CHECK (onlink IN (0, 1)),

     protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     applied INTEGER NOT NULL DEFAULT 0 CHECK (applied IN (0, 1)),
     pending_delete INTEGER NOT NULL DEFAULT 0 CHECK (pending_delete IN (0, 1)),

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (table_id) REFERENCES routing_tables(table_id)
);

-- Stores optional multipath nexthops for routes that use repeated "nexthop" clauses.
CREATE TABLE IF NOT EXISTS route_nexthops (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     route_id INTEGER NOT NULL,
     nexthop_order INTEGER NOT NULL DEFAULT 0,

     gateway TEXT,
     dev TEXT,
     weight INTEGER CHECK (weight IS NULL OR weight > 0),
     onlink INTEGER NOT NULL DEFAULT 0 CHECK (onlink IN (0, 1)),

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE
);

-- Stores policy routing rules that map to the Linux "ip rule" command.
CREATE TABLE IF NOT EXISTS routing_rules (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     rule_order INTEGER NOT NULL DEFAULT 0,

     addr_family TEXT NOT NULL CHECK (addr_family IN ('ipv4', 'ipv6')),
     priority INTEGER NOT NULL CHECK (priority >= 0),

     source_addr TEXT,
     destination_addr TEXT,
     incoming_iface TEXT,
     outgoing_iface TEXT,

     fwmark TEXT,
     fwmask TEXT,
     tos TEXT,
     dsfield TEXT,

     ip_proto TEXT,
     sport TEXT,
     dport TEXT,
     uid_range TEXT,

     action TEXT NOT NULL DEFAULT 'lookup' CHECK (
          action IN (
               'lookup',
               'blackhole',
               'unreachable',
               'prohibit'
          )
     ),
     table_id INTEGER,

     suppress_prefixlength INTEGER CHECK (
          suppress_prefixlength IS NULL OR suppress_prefixlength >= 0
     ),
     suppress_ifgroup TEXT,
     realms TEXT,
     goto_priority INTEGER CHECK (goto_priority IS NULL OR goto_priority >= 0),

     protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     applied INTEGER NOT NULL DEFAULT 0 CHECK (applied IN (0, 1)),
     pending_delete INTEGER NOT NULL DEFAULT 0 CHECK (pending_delete IN (0, 1)),

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (table_id) REFERENCES routing_tables(table_id),
     CHECK (
          (action = 'lookup' AND table_id IS NOT NULL)
          OR
          (action IN ('blackhole', 'unreachable', 'prohibit') AND table_id IS NULL)
     )
);

CREATE INDEX IF NOT EXISTS idx_routing_tables_table_id
ON routing_tables (table_id);

CREATE INDEX IF NOT EXISTS idx_routes_family_table
ON routes (addr_family, table_id, enabled, pending_delete);

CREATE INDEX IF NOT EXISTS idx_routes_destination
ON routes (addr_family, destination);

CREATE INDEX IF NOT EXISTS idx_route_nexthops_route
ON route_nexthops (route_id, nexthop_order);

CREATE UNIQUE INDEX IF NOT EXISTS idx_routing_rules_priority_family
ON routing_rules (addr_family, priority);

CREATE INDEX IF NOT EXISTS idx_routing_rules_table
ON routing_rules (table_id, enabled, pending_delete);

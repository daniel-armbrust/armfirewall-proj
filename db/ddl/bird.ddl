PRAGMA foreign_keys = ON;

-- Stores singleton BIRD global configuration.
CREATE TABLE IF NOT EXISTS global_cfg (
     id INTEGER PRIMARY KEY CHECK (id = 1),
     router_id TEXT NOT NULL DEFAULT '192.0.2.1',
     hostname TEXT NOT NULL DEFAULT 'armfirewall',
     debug_enabled INTEGER NOT NULL DEFAULT 0 CHECK (debug_enabled IN (0, 1)),
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Stores BIRD channel configuration shared by routing protocols.
-- External references:
--   - table_name should match routing_tables.table_name in policy-routing.db when set.
CREATE TABLE IF NOT EXISTS channel (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     family TEXT NOT NULL CHECK (family IN ('ipv4', 'ipv6', 'ipv4/ipv6')),
     table_name TEXT,
     import_policy TEXT NOT NULL DEFAULT 'all' CHECK (import_policy IN ('all', 'none')),
     export_policy TEXT NOT NULL DEFAULT 'none' CHECK (export_policy IN ('all', 'none')),
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     UNIQUE (family, table_name, import_policy, export_policy)
);

-- Stores BIRD kernel protocol configuration.
-- External references:
--   - route_table should match routing_tables.table_id in policy-routing.db.
CREATE TABLE IF NOT EXISTS proto_kernel (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     route_table INTEGER NOT NULL CHECK (route_table BETWEEN 1 AND 4294967295),
     learn TEXT CHECK (learn IS NULL OR learn = 'all'),
     channel_id INTEGER NOT NULL,
     metric INTEGER NOT NULL DEFAULT 32 CHECK (metric >= 0),
     scan_time_secs INTEGER NOT NULL DEFAULT 10 CHECK (scan_time_secs BETWEEN 1 AND 86400),
     persist INTEGER NOT NULL DEFAULT 1 CHECK (persist IN (0, 1)),
     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     FOREIGN KEY (channel_id) REFERENCES channel(id) ON DELETE RESTRICT,
     UNIQUE (route_table, channel_id)
);

-- Stores BIRD device protocol configuration. The renderer should emit both
-- hardcoded channel blocks: ipv4; and ipv6;.
-- External references:
--   - iface_name should match ifaces.name in iface.db.
CREATE TABLE IF NOT EXISTS proto_device (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     scan_time_secs INTEGER NOT NULL DEFAULT 10 CHECK (scan_time_secs BETWEEN 1 AND 86400),
     iface_name TEXT NOT NULL,
     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     UNIQUE (iface_name)
);

-- Stores BIRD direct protocol configuration. The renderer should emit both
-- hardcoded channel blocks: ipv4; and ipv6;.
-- External references:
--   - iface_name should match ifaces.name in iface.db.
CREATE TABLE IF NOT EXISTS proto_direct (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     iface_name TEXT NOT NULL,
     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     UNIQUE (iface_name)
);

-- Stores BIRD RIP/RIPng protocol configuration.
CREATE TABLE IF NOT EXISTS proto_rip (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     version TEXT NOT NULL DEFAULT '2' CHECK (version IN ('1', '2', 'ng')),
     mode TEXT NOT NULL DEFAULT 'multicast' CHECK (mode IN ('multicast', 'broadcast')),
     iface_names TEXT NOT NULL DEFAULT '["*"]',
     import_policy TEXT NOT NULL DEFAULT 'all' CHECK (import_policy IN ('all', 'none')),
     export_policy TEXT NOT NULL DEFAULT 'none' CHECK (export_policy IN ('all', 'none')),
     multicast_addr TEXT NOT NULL DEFAULT '224.0.0.9',
     passive INTEGER NOT NULL DEFAULT 0 CHECK (passive IN (0, 1)),
     port INTEGER NOT NULL DEFAULT 520 CHECK (port IN (520, 521)),
     update_time_secs INTEGER NOT NULL DEFAULT 30 CHECK (update_time_secs BETWEEN 1 AND 86400),
     timeout_time_secs INTEGER NOT NULL DEFAULT 180 CHECK (timeout_time_secs BETWEEN 1 AND 86400),
     garbage_time_secs INTEGER NOT NULL DEFAULT 120 CHECK (garbage_time_secs BETWEEN 1 AND 86400),
     authentication TEXT NOT NULL DEFAULT 'none' CHECK (authentication IN ('none', 'plaintext', 'cryptographic')),
     password TEXT,
     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     CHECK (
          (version = '1' AND mode = 'broadcast' AND multicast_addr = '255.255.255.255' AND port = 520)
          OR
          (version = '2' AND mode = 'multicast' AND multicast_addr = '224.0.0.9' AND port = 520)
          OR
          (version = '2' AND mode = 'broadcast' AND multicast_addr = '255.255.255.255' AND port = 520)
          OR
          (version = 'ng' AND multicast_addr = 'ff02::9' AND port = 521 AND mode = 'multicast')
     ),
     CHECK (
          authentication = 'none'
          OR
          length(trim(COALESCE(password, ''))) > 0
     )
);

-- Stores each BIRD diagnostic command execution. The collector should insert one
-- row per birdctl command run, then attach parsed rows to command_id.
CREATE TABLE IF NOT EXISTS diagnostic_command_run (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     command TEXT NOT NULL,
     exit_code INTEGER NOT NULL DEFAULT 0,
     stdout TEXT,
     stderr TEXT,
     duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
     collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Stores parsed output from: birdctl show protocols.
-- Expected columns from BIRD are: Name, Proto, Table, State, Since and Info.
CREATE TABLE IF NOT EXISTS diagnostic_protocol (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     command_id INTEGER NOT NULL,
     name TEXT NOT NULL,
     proto TEXT NOT NULL,
     table_name TEXT,
     state TEXT NOT NULL,
     since TEXT,
     info TEXT,
     raw_line TEXT NOT NULL,
     collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     FOREIGN KEY (command_id) REFERENCES diagnostic_command_run(id) ON DELETE CASCADE,
     UNIQUE (command_id, name)
);

CREATE INDEX IF NOT EXISTS idx_bird_diagnostic_command_run_command
ON diagnostic_command_run (command, collected_at);

CREATE INDEX IF NOT EXISTS idx_bird_diagnostic_protocol_command
ON diagnostic_protocol (command_id);

CREATE INDEX IF NOT EXISTS idx_bird_diagnostic_protocol_proto_state
ON diagnostic_protocol (proto, state);

-- Stores structured RIP routes imported by the RIP protocol.
CREATE TABLE IF NOT EXISTS rip_imported_routes (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     command_id INTEGER NOT NULL,
     table_name TEXT,
     route_prefix TEXT NOT NULL,
     route_type TEXT,
     source_protocol TEXT,
     since TEXT,
     selected INTEGER NOT NULL DEFAULT 0 CHECK (selected IN (0, 1)),
     metric INTEGER,
     next_hop TEXT,
     iface_name TEXT,
     raw_route TEXT NOT NULL,
     raw_detail TEXT,
     collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     FOREIGN KEY (command_id) REFERENCES diagnostic_command_run(id) ON DELETE CASCADE
);

-- Stores structured RIP routes exported by the RIP protocol.
CREATE TABLE IF NOT EXISTS rip_exported_routes (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     command_id INTEGER NOT NULL,
     table_name TEXT,
     route_prefix TEXT NOT NULL,
     route_type TEXT,
     source_protocol TEXT,
     since TEXT,
     selected INTEGER NOT NULL DEFAULT 0 CHECK (selected IN (0, 1)),
     metric INTEGER,
     next_hop TEXT,
     iface_name TEXT,
     raw_route TEXT NOT NULL,
     raw_detail TEXT,
     collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     FOREIGN KEY (command_id) REFERENCES diagnostic_command_run(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bird_rip_imported_routes_command
ON rip_imported_routes (command_id);

CREATE INDEX IF NOT EXISTS idx_bird_rip_imported_routes_prefix
ON rip_imported_routes (route_prefix);

CREATE INDEX IF NOT EXISTS idx_bird_rip_exported_routes_command
ON rip_exported_routes (command_id);

CREATE INDEX IF NOT EXISTS idx_bird_rip_exported_routes_prefix
ON rip_exported_routes (route_prefix);

CREATE INDEX IF NOT EXISTS idx_bird_channel_family
ON channel (family);

CREATE INDEX IF NOT EXISTS idx_bird_channel_table_name
ON channel (table_name);

CREATE INDEX IF NOT EXISTS idx_bird_proto_kernel_route_table
ON proto_kernel (route_table);

CREATE INDEX IF NOT EXISTS idx_bird_proto_kernel_channel
ON proto_kernel (channel_id);

CREATE INDEX IF NOT EXISTS idx_bird_proto_device_iface
ON proto_device (iface_name);

CREATE INDEX IF NOT EXISTS idx_bird_proto_direct_iface
ON proto_direct (iface_name);

CREATE INDEX IF NOT EXISTS idx_bird_proto_rip_version
ON proto_rip (version, enabled);

CREATE TRIGGER IF NOT EXISTS trg_bird_global_cfg_touch_updated_at
AFTER UPDATE ON global_cfg
FOR EACH ROW
BEGIN
     UPDATE global_cfg
        SET updated_at = CURRENT_TIMESTAMP
      WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_bird_channel_touch_updated_at
AFTER UPDATE ON channel
FOR EACH ROW
BEGIN
     UPDATE channel
        SET updated_at = CURRENT_TIMESTAMP
      WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_bird_proto_kernel_touch_updated_at
AFTER UPDATE ON proto_kernel
FOR EACH ROW
BEGIN
     UPDATE proto_kernel
        SET updated_at = CURRENT_TIMESTAMP
      WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_bird_proto_device_touch_updated_at
AFTER UPDATE ON proto_device
FOR EACH ROW
BEGIN
     UPDATE proto_device
        SET updated_at = CURRENT_TIMESTAMP
      WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_bird_proto_direct_touch_updated_at
AFTER UPDATE ON proto_direct
FOR EACH ROW
BEGIN
     UPDATE proto_direct
        SET updated_at = CURRENT_TIMESTAMP
      WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_bird_proto_rip_touch_updated_at
AFTER UPDATE ON proto_rip
FOR EACH ROW
BEGIN
     UPDATE proto_rip
        SET updated_at = CURRENT_TIMESTAMP
      WHERE id = OLD.id;
END;

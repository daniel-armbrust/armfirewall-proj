PRAGMA foreign_keys = ON;

-- Stores Libreswan IPsec tunnel definitions managed by ArmFirewall.
CREATE TABLE IF NOT EXISTS libreswan_connections (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     conn_name TEXT NOT NULL UNIQUE,
     description TEXT NOT NULL DEFAULT '',
     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     left_addr TEXT NOT NULL,
     left_id TEXT NOT NULL DEFAULT '',
     right_addr TEXT NOT NULL,
     authby TEXT NOT NULL DEFAULT 'secret',
     shared_secret TEXT NOT NULL CHECK (length(trim(shared_secret)) > 0),
     leftsubnet TEXT NOT NULL DEFAULT '0.0.0.0/0',
     rightsubnet TEXT NOT NULL DEFAULT '0.0.0.0/0',
     auto TEXT NOT NULL DEFAULT 'start' CHECK (auto IN ('add', 'ondemand', 'route', 'start', 'ignore')),
     mark TEXT NOT NULL,
     vti_interface TEXT NOT NULL,
     vti_routing TEXT NOT NULL DEFAULT 'no' CHECK (vti_routing IN ('yes', 'no')),
     ikev2 TEXT NOT NULL DEFAULT 'no' CHECK (ikev2 IN ('no', 'never', 'permit', 'propose', 'insist', 'yes')),
     ike TEXT NOT NULL DEFAULT 'aes_cbc256-sha2_384;modp1536',
     phase2alg TEXT NOT NULL DEFAULT 'aes_gcm256;modp1536',
     encapsulation TEXT NOT NULL DEFAULT 'yes' CHECK (encapsulation IN ('yes', 'no', 'auto')),
     ikelifetime TEXT NOT NULL DEFAULT '28800s',
     salifetime TEXT NOT NULL DEFAULT '3600s',
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     CHECK (left_addr <> right_addr)
);

CREATE INDEX IF NOT EXISTS idx_libreswan_connections_enabled
ON libreswan_connections (enabled, conn_name);

CREATE UNIQUE INDEX IF NOT EXISTS idx_libreswan_connections_conn_name
ON libreswan_connections (conn_name);

CREATE UNIQUE INDEX IF NOT EXISTS idx_libreswan_connections_right_addr
ON libreswan_connections (right_addr);

CREATE UNIQUE INDEX IF NOT EXISTS idx_libreswan_connections_mark
ON libreswan_connections (mark);

CREATE TRIGGER IF NOT EXISTS trg_libreswan_connections_shared_secret_insert
BEFORE INSERT ON libreswan_connections
FOR EACH ROW
WHEN length(trim(NEW.shared_secret)) = 0
BEGIN
     SELECT RAISE(ABORT, 'Shared secret is required.');
END;

CREATE TRIGGER IF NOT EXISTS trg_libreswan_connections_shared_secret_update
BEFORE UPDATE OF shared_secret ON libreswan_connections
FOR EACH ROW
WHEN length(trim(NEW.shared_secret)) = 0
BEGIN
     SELECT RAISE(ABORT, 'Shared secret is required.');
END;

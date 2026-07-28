PRAGMA foreign_keys = ON;

-- Stores extensible runtime configuration values.
-- Secret values should be kept outside SQLite and referenced by a protected path.
CREATE TABLE IF NOT EXISTS runtime_settings (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     setting_key TEXT NOT NULL UNIQUE CHECK (length(trim(setting_key)) > 0),
     setting_value TEXT,
     value_type TEXT NOT NULL DEFAULT 'string' CHECK (
          value_type IN ('string', 'integer', 'number', 'boolean', 'json')
     ),
     is_secret INTEGER NOT NULL DEFAULT 0 CHECK (is_secret IN (0, 1)),
     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_runtime_settings_enabled
ON runtime_settings (enabled, setting_key);

-- Stores the singleton OCI authentication configuration.
-- Private key material is intentionally not stored in this database.
CREATE TABLE IF NOT EXISTS oci_integration (
     id INTEGER PRIMARY KEY CHECK (id = 1),
     authentication_type TEXT NOT NULL DEFAULT 'instance_principal' CHECK (
          authentication_type IN ('instance_principal', 'api_key')
     ),
     user_ocid TEXT,
     tenancy_ocid TEXT,
     fingerprint TEXT,
     region TEXT,
     profile_name TEXT,
     private_key_filepath TEXT,
     private_key_sha256 TEXT CHECK (
          private_key_sha256 IS NULL OR length(private_key_sha256) = 64
     ),
     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     last_authentication_test_at TEXT,
     last_authentication_test_status TEXT CHECK (
          last_authentication_test_status IS NULL
          OR last_authentication_test_status IN ('success', 'failed')
     ),
     last_authentication_test_error TEXT,
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     CHECK (
          authentication_type = 'instance_principal'
          OR (
               length(trim(COALESCE(user_ocid, ''))) > 0
               AND length(trim(COALESCE(tenancy_ocid, ''))) > 0
               AND length(trim(COALESCE(private_key_filepath, ''))) > 0
          )
     )
);

CREATE TRIGGER IF NOT EXISTS runtime_settings_touch_updated_at
AFTER UPDATE ON runtime_settings
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
     UPDATE runtime_settings
        SET updated_at = CURRENT_TIMESTAMP
      WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS oci_integration_touch_updated_at
AFTER UPDATE ON oci_integration
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
     UPDATE oci_integration
        SET updated_at = CURRENT_TIMESTAMP
      WHERE id = OLD.id;
END;

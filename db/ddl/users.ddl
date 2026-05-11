PRAGMA foreign_keys = ON;

-- Stores local web GUI users allowed to authenticate in ArmFirewall.
CREATE TABLE IF NOT EXISTS users (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     username TEXT NOT NULL UNIQUE CHECK (length(username) BETWEEN 3 AND 64),
     display_name TEXT,

     password_hash TEXT NOT NULL,
     password_changed_at TEXT,
     must_change_password INTEGER NOT NULL DEFAULT 0 CHECK (must_change_password IN (0, 1)),

     role TEXT NOT NULL DEFAULT 'admin' CHECK (
          role IN (
               'admin',
               'operator',
               'viewer'
          )
     ),

     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),

     failed_login_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
     locked_until TEXT,
     last_login_at TEXT,
     last_login_ip TEXT,

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Stores active browser sessions using only a hash of the generated token.
CREATE TABLE IF NOT EXISTS user_sessions (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     user_id INTEGER NOT NULL,
     session_token_hash TEXT NOT NULL UNIQUE,

     remote_addr TEXT,
     user_agent TEXT,

     expires_at TEXT NOT NULL,
     revoked_at TEXT,
     last_seen_at TEXT,

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Stores authentication audit events for successful and failed login activity.
CREATE TABLE IF NOT EXISTS user_login_events (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     user_id INTEGER,
     username TEXT NOT NULL,
     event_type TEXT NOT NULL CHECK (
          event_type IN (
               'success',
               'failed',
               'logout',
               'locked',
               'password_change'
          )
     ),
     remote_addr TEXT,
     user_agent TEXT,
     message TEXT,
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Speeds up user lookup during authentication.
CREATE INDEX IF NOT EXISTS idx_users_username
ON users (username);

-- Speeds up user lookup by role and enabled state.
CREATE INDEX IF NOT EXISTS idx_users_role_enabled
ON users (role, enabled);

-- Speeds up session lookup by token hash.
CREATE INDEX IF NOT EXISTS idx_user_sessions_token_hash
ON user_sessions (session_token_hash);

-- Speeds up session cleanup by expiration date.
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at
ON user_sessions (expires_at);

-- Speeds up authentication audit lookup by user and date.
CREATE INDEX IF NOT EXISTS idx_user_login_events_user_created_at
ON user_login_events (user_id, created_at);

-- Speeds up authentication audit lookup by event type and date.
CREATE INDEX IF NOT EXISTS idx_user_login_events_type_created_at
ON user_login_events (event_type, created_at);

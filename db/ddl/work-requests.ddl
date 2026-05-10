PRAGMA foreign_keys = ON;

-- Stores work request categories mapped to operating system targets.
CREATE TABLE IF NOT EXISTS work_request_categories (
     name TEXT PRIMARY KEY,
     category TEXT NOT NULL CHECK (
          category IN (
               'FIREWALL_RULES',
               'NAT_RULES',
               'MANGLE_RULES',
               'POLICY_ROUTING'
          )
     ),
     family TEXT CHECK (family IN ('IPV4', 'IPV6')),
     target_name TEXT NOT NULL,
     description TEXT NOT NULL
);

INSERT OR IGNORE INTO work_request_categories (name, category, family, target_name, description) VALUES
     ('FIREWALL_RULES.IPV4.filter_input_rules', 'FIREWALL_RULES', 'IPV4', 'filter_input_rules', 'IPv4 filter INPUT chain rules.'),
     ('FIREWALL_RULES.IPV4.filter_forward_rules', 'FIREWALL_RULES', 'IPV4', 'filter_forward_rules', 'IPv4 filter FORWARD chain rules.'),
     ('FIREWALL_RULES.IPV4.filter_output_rules', 'FIREWALL_RULES', 'IPV4', 'filter_output_rules', 'IPv4 filter OUTPUT chain rules.'),
     ('FIREWALL_RULES.IPV6.filter_input_rules', 'FIREWALL_RULES', 'IPV6', 'filter_input_rules', 'IPv6 filter INPUT chain rules.'),
     ('FIREWALL_RULES.IPV6.filter_forward_rules', 'FIREWALL_RULES', 'IPV6', 'filter_forward_rules', 'IPv6 filter FORWARD chain rules.'),
     ('FIREWALL_RULES.IPV6.filter_output_rules', 'FIREWALL_RULES', 'IPV6', 'filter_output_rules', 'IPv6 filter OUTPUT chain rules.'),
     ('NAT_RULES.IPV4.nat_prerouting_rules', 'NAT_RULES', 'IPV4', 'nat_prerouting_rules', 'IPv4 NAT PREROUTING chain rules.'),
     ('NAT_RULES.IPV4.nat_input_rules', 'NAT_RULES', 'IPV4', 'nat_input_rules', 'IPv4 NAT INPUT chain rules.'),
     ('NAT_RULES.IPV4.nat_output_rules', 'NAT_RULES', 'IPV4', 'nat_output_rules', 'IPv4 NAT OUTPUT chain rules.'),
     ('NAT_RULES.IPV4.nat_postrouting_rules', 'NAT_RULES', 'IPV4', 'nat_postrouting_rules', 'IPv4 NAT POSTROUTING chain rules.'),
     ('NAT_RULES.IPV6.nat_prerouting_rules', 'NAT_RULES', 'IPV6', 'nat_prerouting_rules', 'IPv6 NAT PREROUTING chain rules.'),
     ('NAT_RULES.IPV6.nat_input_rules', 'NAT_RULES', 'IPV6', 'nat_input_rules', 'IPv6 NAT INPUT chain rules.'),
     ('NAT_RULES.IPV6.nat_output_rules', 'NAT_RULES', 'IPV6', 'nat_output_rules', 'IPv6 NAT OUTPUT chain rules.'),
     ('NAT_RULES.IPV6.nat_postrouting_rules', 'NAT_RULES', 'IPV6', 'nat_postrouting_rules', 'IPv6 NAT POSTROUTING chain rules.'),
     ('MANGLE_RULES.IPV4.mangle_prerouting_rules', 'MANGLE_RULES', 'IPV4', 'mangle_prerouting_rules', 'IPv4 mangle PREROUTING chain rules.'),
     ('MANGLE_RULES.IPV4.mangle_input_rules', 'MANGLE_RULES', 'IPV4', 'mangle_input_rules', 'IPv4 mangle INPUT chain rules.'),
     ('MANGLE_RULES.IPV4.mangle_forward_rules', 'MANGLE_RULES', 'IPV4', 'mangle_forward_rules', 'IPv4 mangle FORWARD chain rules.'),
     ('MANGLE_RULES.IPV4.mangle_output_rules', 'MANGLE_RULES', 'IPV4', 'mangle_output_rules', 'IPv4 mangle OUTPUT chain rules.'),
     ('MANGLE_RULES.IPV4.mangle_postrouting_rules', 'MANGLE_RULES', 'IPV4', 'mangle_postrouting_rules', 'IPv4 mangle POSTROUTING chain rules.'),
     ('MANGLE_RULES.IPV6.mangle_prerouting_rules', 'MANGLE_RULES', 'IPV6', 'mangle_prerouting_rules', 'IPv6 mangle PREROUTING chain rules.'),
     ('MANGLE_RULES.IPV6.mangle_input_rules', 'MANGLE_RULES', 'IPV6', 'mangle_input_rules', 'IPv6 mangle INPUT chain rules.'),
     ('MANGLE_RULES.IPV6.mangle_forward_rules', 'MANGLE_RULES', 'IPV6', 'mangle_forward_rules', 'IPv6 mangle FORWARD chain rules.'),
     ('MANGLE_RULES.IPV6.mangle_output_rules', 'MANGLE_RULES', 'IPV6', 'mangle_output_rules', 'IPv6 mangle OUTPUT chain rules.'),
     ('MANGLE_RULES.IPV6.mangle_postrouting_rules', 'MANGLE_RULES', 'IPV6', 'mangle_postrouting_rules', 'IPv6 mangle POSTROUTING chain rules.'),
     ('POLICY_ROUTING.IPV4.main', 'POLICY_ROUTING', 'IPV4', 'main', 'IPv4 policy routing changes.'),
     ('POLICY_ROUTING.IPV6.main', 'POLICY_ROUTING', 'IPV6', 'main', 'IPv6 policy routing changes.');

-- Stores daemon handlers used to execute each work request category.
CREATE TABLE IF NOT EXISTS work_request_handlers (
     category TEXT PRIMARY KEY CHECK (
          category IN (
               'FIREWALL_RULES',
               'NAT_RULES',
               'MANGLE_RULES',
               'POLICY_ROUTING'
          )
     ),
     script_name TEXT NOT NULL CHECK (
          script_name NOT LIKE '%/%'
          AND script_name NOT LIKE '%..%'
          AND script_name LIKE '%.py'
     ),
     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     description TEXT NOT NULL
);

INSERT OR IGNORE INTO work_request_handlers (category, script_name, enabled, description) VALUES
     ('FIREWALL_RULES', 'fwrulesd.py', 1, 'Applies filter table firewall rules.'),
     ('NAT_RULES', 'fwrulesd.py', 1, 'Applies NAT table firewall rules.'),
     ('MANGLE_RULES', 'fwrulesd.py', 1, 'Applies mangle table firewall rules.'),
     ('POLICY_ROUTING', 'proutes.py', 1, 'Applies policy routing changes.');

-- Stores allowed operations accepted by the work queue.
CREATE TABLE IF NOT EXISTS work_request_actions (
     name TEXT PRIMARY KEY,
     description TEXT NOT NULL
);

INSERT OR IGNORE INTO work_request_actions (name, description) VALUES
     ('apply', 'Apply a requested change to the operating system.'),
     ('remove', 'Remove a configured item from the operating system.'),
     ('change', 'Change an existing item in the operating system.');

-- Stores asynchronous operating system changes requested by the GUI.
CREATE TABLE IF NOT EXISTS work_requests (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     request_uid TEXT NOT NULL UNIQUE,

     source TEXT NOT NULL DEFAULT 'gui' CHECK (source IN ('gui', 'api', 'daemon', 'system')),
     category_name TEXT NOT NULL,
     action_name TEXT NOT NULL,
     target_rule_id INTEGER,

     priority INTEGER NOT NULL DEFAULT 100 CHECK (priority BETWEEN 0 AND 999),
     status TEXT NOT NULL DEFAULT 'queue' CHECK (
          status IN (
               'queue',
               'running',
               'success',
               'failed'
          )
     ),

     payload_json TEXT NOT NULL DEFAULT '{}',
     -- Stores the operating system error message when execution fails.
     error_message TEXT,

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (category_name) REFERENCES work_request_categories(name),
     FOREIGN KEY (action_name) REFERENCES work_request_actions(name)
);

-- Stores status transitions and execution notes for work requests.
CREATE TABLE IF NOT EXISTS work_request_events (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     work_request_id INTEGER NOT NULL,
     event_type TEXT NOT NULL CHECK (
          event_type IN (
               'queue',
               'running',
               'success',
               'failed'
          )
     ),
     message TEXT,
     details_json TEXT,
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     FOREIGN KEY (work_request_id) REFERENCES work_requests(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_work_requests_queue
ON work_requests (status, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_work_requests_category_action
ON work_requests (category_name, action_name, status);

CREATE INDEX IF NOT EXISTS idx_work_requests_request_uid
ON work_requests (request_uid);

CREATE INDEX IF NOT EXISTS idx_work_request_events_request
ON work_request_events (work_request_id, created_at);

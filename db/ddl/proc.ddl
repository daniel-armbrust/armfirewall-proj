PRAGMA foreign_keys = ON;

-- Stores global Linux kernel parameters exposed through /proc/sys.
CREATE TABLE IF NOT EXISTS proc (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     category TEXT NOT NULL,
     name TEXT NOT NULL UNIQUE,
     proc_path TEXT NOT NULL UNIQUE,
     description TEXT NOT NULL,
     default_value TEXT NOT NULL,
     current_value TEXT,
     desired_value TEXT,
     protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
     enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
     collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO proc (
     category,
     name,
     proc_path,
     description,
     default_value,
     desired_value
) VALUES
     ('IPv4', 'net.ipv4.ip_forward', '/proc/sys/net/ipv4/ip_forward', 'Enables IPv4 packet forwarding between interfaces.', '0', '0'),
     ('IPv4', 'net.ipv4.conf.all.rp_filter', '/proc/sys/net/ipv4/conf/all/rp_filter', 'Controls global reverse path filtering for IPv4 source validation.', '0', '0'),
     ('IPv4', 'net.ipv4.conf.default.rp_filter', '/proc/sys/net/ipv4/conf/default/rp_filter', 'Controls reverse path filtering inherited by new IPv4 interfaces.', '0', '0'),
     ('IPv4', 'net.ipv4.conf.all.accept_redirects', '/proc/sys/net/ipv4/conf/all/accept_redirects', 'Controls whether IPv4 ICMP redirect messages are accepted globally.', '1', '1'),
     ('IPv4', 'net.ipv4.conf.default.accept_redirects', '/proc/sys/net/ipv4/conf/default/accept_redirects', 'Controls whether new IPv4 interfaces accept ICMP redirect messages.', '1', '1'),
     ('IPv4', 'net.ipv4.conf.all.send_redirects', '/proc/sys/net/ipv4/conf/all/send_redirects', 'Controls whether IPv4 ICMP redirect messages are sent globally.', '1', '1'),
     ('IPv4', 'net.ipv4.conf.default.send_redirects', '/proc/sys/net/ipv4/conf/default/send_redirects', 'Controls whether new IPv4 interfaces send ICMP redirect messages.', '1', '1'),
     ('IPv4', 'net.ipv4.conf.all.secure_redirects', '/proc/sys/net/ipv4/conf/all/secure_redirects', 'Controls whether secure IPv4 redirects from known gateways are accepted globally.', '1', '1'),
     ('IPv4', 'net.ipv4.conf.default.secure_redirects', '/proc/sys/net/ipv4/conf/default/secure_redirects', 'Controls whether new IPv4 interfaces accept secure redirects from known gateways.', '1', '1'),

     ('TCP', 'net.ipv4.tcp_syncookies', '/proc/sys/net/ipv4/tcp_syncookies', 'Enables SYN cookies to help protect against SYN flood attacks.', '1', '1'),
     ('TCP', 'net.ipv4.tcp_timestamps', '/proc/sys/net/ipv4/tcp_timestamps', 'Enables TCP timestamps used by PAWS and round-trip time measurement.', '1', '1'),
     ('TCP', 'net.ipv4.tcp_sack', '/proc/sys/net/ipv4/tcp_sack', 'Enables TCP selective acknowledgements.', '1', '1'),
     ('TCP', 'net.ipv4.tcp_window_scaling', '/proc/sys/net/ipv4/tcp_window_scaling', 'Enables TCP window scaling for high bandwidth-delay paths.', '1', '1'),
     ('TCP', 'net.ipv4.tcp_fin_timeout', '/proc/sys/net/ipv4/tcp_fin_timeout', 'Defines how long sockets stay in FIN-WAIT-2 before timeout.', '60', '60'),
     ('TCP', 'net.ipv4.tcp_keepalive_time', '/proc/sys/net/ipv4/tcp_keepalive_time', 'Defines idle time before TCP starts sending keepalive probes.', '7200', '7200'),
     ('TCP', 'net.ipv4.tcp_keepalive_intvl', '/proc/sys/net/ipv4/tcp_keepalive_intvl', 'Defines the interval between TCP keepalive probes.', '75', '75'),
     ('TCP', 'net.ipv4.tcp_keepalive_probes', '/proc/sys/net/ipv4/tcp_keepalive_probes', 'Defines how many TCP keepalive probes are sent before dropping a connection.', '9', '9'),
     ('TCP', 'net.ipv4.tcp_max_syn_backlog', '/proc/sys/net/ipv4/tcp_max_syn_backlog', 'Defines the maximum queued half-open TCP connection requests.', 'system-dependent', NULL),
     ('TCP', 'net.ipv4.tcp_syn_retries', '/proc/sys/net/ipv4/tcp_syn_retries', 'Defines how many SYN retransmits are attempted for outbound TCP connections.', '6', '6'),
     ('TCP', 'net.ipv4.tcp_synack_retries', '/proc/sys/net/ipv4/tcp_synack_retries', 'Defines how many SYN-ACK retransmits are attempted for passive TCP opens.', '5', '5'),
     ('TCP', 'net.ipv4.tcp_retries2', '/proc/sys/net/ipv4/tcp_retries2', 'Defines how many retransmits are attempted before killing an established TCP connection.', '15', '15'),

     ('ICMP', 'net.ipv4.icmp_echo_ignore_all', '/proc/sys/net/ipv4/icmp_echo_ignore_all', 'Controls whether the host ignores all ICMP echo requests.', '0', '0'),
     ('ICMP', 'net.ipv4.icmp_echo_ignore_broadcasts', '/proc/sys/net/ipv4/icmp_echo_ignore_broadcasts', 'Controls whether ICMP echo requests sent to broadcast addresses are ignored.', '1', '1'),
     ('ICMP', 'net.ipv4.icmp_ignore_bogus_error_responses', '/proc/sys/net/ipv4/icmp_ignore_bogus_error_responses', 'Controls whether bogus ICMP error responses are ignored.', '1', '1'),
     ('ICMP', 'net.ipv4.icmp_ratelimit', '/proc/sys/net/ipv4/icmp_ratelimit', 'Defines the minimum spacing in milliseconds between certain ICMP replies.', '1000', '1000'),
     ('ICMP', 'net.ipv4.icmp_ratemask', '/proc/sys/net/ipv4/icmp_ratemask', 'Defines which ICMP message types are subject to rate limiting.', '6168', '6168'),

     ('Neighbor', 'net.ipv4.neigh.default.gc_thresh1', '/proc/sys/net/ipv4/neigh/default/gc_thresh1', 'Defines the first garbage collection threshold for IPv4 neighbor entries.', '128', '128'),
     ('Neighbor', 'net.ipv4.neigh.default.gc_thresh2', '/proc/sys/net/ipv4/neigh/default/gc_thresh2', 'Defines the second garbage collection threshold for IPv4 neighbor entries.', '512', '512'),
     ('Neighbor', 'net.ipv4.neigh.default.gc_thresh3', '/proc/sys/net/ipv4/neigh/default/gc_thresh3', 'Defines the hard garbage collection threshold for IPv4 neighbor entries.', '1024', '1024'),
     ('Neighbor', 'net.ipv4.neigh.default.base_reachable_time_ms', '/proc/sys/net/ipv4/neigh/default/base_reachable_time_ms', 'Defines the base reachable time in milliseconds for IPv4 neighbor entries.', '30000', '30000'),
     ('Neighbor', 'net.ipv4.neigh.default.retrans_time_ms', '/proc/sys/net/ipv4/neigh/default/retrans_time_ms', 'Defines retransmission time in milliseconds for IPv4 neighbor discovery.', '1000', '1000'),

     ('IPv6', 'net.ipv6.conf.all.forwarding', '/proc/sys/net/ipv6/conf/all/forwarding', 'Enables IPv6 packet forwarding globally.', '0', '0'),
     ('IPv6', 'net.ipv6.conf.default.forwarding', '/proc/sys/net/ipv6/conf/default/forwarding', 'Controls IPv6 forwarding inherited by new interfaces.', '0', '0'),
     ('IPv6', 'net.ipv6.conf.all.accept_redirects', '/proc/sys/net/ipv6/conf/all/accept_redirects', 'Controls whether IPv6 redirect messages are accepted globally.', '1', '1'),
     ('IPv6', 'net.ipv6.conf.default.accept_redirects', '/proc/sys/net/ipv6/conf/default/accept_redirects', 'Controls whether new IPv6 interfaces accept redirect messages.', '1', '1'),
     ('IPv6', 'net.ipv6.conf.all.accept_ra', '/proc/sys/net/ipv6/conf/all/accept_ra', 'Controls whether IPv6 router advertisements are accepted globally.', '1', '1'),
     ('IPv6', 'net.ipv6.conf.default.accept_ra', '/proc/sys/net/ipv6/conf/default/accept_ra', 'Controls whether new IPv6 interfaces accept router advertisements.', '1', '1'),
     ('IPv6', 'net.ipv6.conf.all.disable_ipv6', '/proc/sys/net/ipv6/conf/all/disable_ipv6', 'Controls whether IPv6 is disabled globally.', '0', '0'),
     ('IPv6', 'net.ipv6.conf.default.disable_ipv6', '/proc/sys/net/ipv6/conf/default/disable_ipv6', 'Controls whether IPv6 is disabled by default on new interfaces.', '0', '0'),

     ('Conntrack', 'net.netfilter.nf_conntrack_max', '/proc/sys/net/netfilter/nf_conntrack_max', 'Defines the maximum number of tracked connections.', 'system-dependent', NULL),
     ('Conntrack', 'net.netfilter.nf_conntrack_tcp_timeout_established', '/proc/sys/net/netfilter/nf_conntrack_tcp_timeout_established', 'Defines established TCP connection tracking timeout in seconds.', '432000', '432000'),
     ('Conntrack', 'net.netfilter.nf_conntrack_tcp_timeout_time_wait', '/proc/sys/net/netfilter/nf_conntrack_tcp_timeout_time_wait', 'Defines TCP TIME-WAIT connection tracking timeout in seconds.', '120', '120'),
     ('Conntrack', 'net.netfilter.nf_conntrack_udp_timeout', '/proc/sys/net/netfilter/nf_conntrack_udp_timeout', 'Defines UDP connection tracking timeout in seconds.', '30', '30'),
     ('Conntrack', 'net.netfilter.nf_conntrack_udp_timeout_stream', '/proc/sys/net/netfilter/nf_conntrack_udp_timeout_stream', 'Defines UDP stream connection tracking timeout in seconds.', '120', '120');

CREATE INDEX IF NOT EXISTS idx_proc_category
ON proc (category);

CREATE INDEX IF NOT EXISTS idx_proc_enabled
ON proc (enabled);

CREATE INDEX IF NOT EXISTS idx_proc_category_enabled
ON proc (category, enabled);

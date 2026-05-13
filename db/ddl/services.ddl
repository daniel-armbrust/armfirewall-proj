CREATE TABLE IF NOT EXISTS services (
    name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    service_group TEXT NOT NULL CHECK(service_group IN ('main', 'optional')),
    protected INTEGER NOT NULL DEFAULT 0 CHECK(protected IN (0, 1)),
    restart_allowed INTEGER NOT NULL DEFAULT 0 CHECK(restart_allowed IN (0, 1)),
    package_name TEXT,
    binary_path TEXT,
    supervisor_program TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TRIGGER IF NOT EXISTS services_touch_updated_at
AFTER UPDATE ON services
FOR EACH ROW
BEGIN
    UPDATE services
       SET updated_at = datetime('now')
     WHERE name = OLD.name;
END;

INSERT OR IGNORE INTO services (
    name, display_name, kind, description, service_group,
    protected, restart_allowed, sort_order
) VALUES
    ('armfirewall-api', 'armfirewall-api', 'web', 'ArmFirewall HTTPS API and web GUI.', 'main', 1, 1, 10),
    ('armfirewall-ifaced', 'armfirewall-ifaced', 'daemon', 'Interface inventory and network metrics collector.', 'main', 1, 0, 20),
    ('armfirewall-monitord', 'armfirewall-monitord', 'daemon', 'RRD monitoring collector and graph generator.', 'main', 0, 0, 30),
    ('armfirewall-workreqd', 'armfirewall-workreqd', 'daemon', 'Work request executor for operating system changes.', 'main', 1, 0, 40),
    ('armfirewall-linkfailover', 'armfirewall-linkfailover', 'daemon', 'Ping-based default route failover daemon.', 'main', 0, 0, 50);

INSERT OR IGNORE INTO services (
    name, display_name, kind, description, service_group,
    protected, restart_allowed, package_name, binary_path, supervisor_program,
    sort_order
) VALUES
    (
        'dnsmasq',
        'Dnsmasq',
        'dns-dhcp',
        'DNS/DHCP service.',
        'optional',
        0,
        0,
        'dnsmasq',
        '/usr/sbin/dnsmasq',
        '[program:dnsmasq]
directory={root}
command=/usr/sbin/dnsmasq --keep-in-foreground --conf-file={root}/conf/dnsmasq.conf --pid-file={root}/logs/dnsmasq.pid
autostart=false
autorestart=true
startsecs=3
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile={root}/logs/dnsmasq.out.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile={root}/logs/dnsmasq.err.log
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=5
',
        100
    ),
    (
        'squid',
        'SQUID Proxy',
        'proxy',
        'Squid proxy service.',
        'optional',
        0,
        0,
        'squid',
        '/usr/sbin/squid',
        '[program:squid]
directory={root}
command=/usr/sbin/squid -N -f /etc/squid/squid.conf
autostart=false
autorestart=true
startsecs=3
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile={root}/logs/squid.out.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile={root}/logs/squid.err.log
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=5
',
        110
    ),
    (
        'bird',
        'BIRD Routing Daemon',
        'routing',
        'Dynamic routing service.',
        'optional',
        0,
        0,
        'bird',
        '/usr/sbin/bird',
        '[program:bird]
directory={root}
command=/bin/sh -c ''if [ -f /etc/bird/bird.conf ]; then exec /usr/sbin/bird -f -c /etc/bird/bird.conf; else exec /usr/sbin/bird -f -c /etc/bird.conf; fi''
autostart=false
autorestart=true
startsecs=3
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile={root}/logs/bird.out.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile={root}/logs/bird.err.log
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=5
',
        120
    );

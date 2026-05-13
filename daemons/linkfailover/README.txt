ArmFirewall Link Failover Daemon
================================

The Link Failover daemon continuously checks configured network links and keeps
the main IPv4 default route on the best healthy interface.

It is a persistent daemon managed by supervisord when the Link Failover service
is enabled. The daemon reads its configuration from linkfailover.db, runs ping
health checks through each configured interface, records link status and events,
and changes the operating system default route when the selected healthy link
changes.

The health check uses the configured target, timeout, attempts, interval and
optional maximum latency threshold. At least two links must be configured for
the failover logic to operate.

Files
-----

__init__.py
    Marks this directory as the daemons.linkfailover Python package.

__main__.py
    Package entry point used by "python -m daemons.linkfailover".

linkfailover.py
    Main daemon process, SQLite reads and writes, ping health checks, event
    persistence, route selection and default route updates.

constants.py
    Database path, log source and ping latency parsing pattern used by the
    daemon.

models.py
    Data classes used to represent configured links and health check results.

common.py
    Shared helper used to parse ping latency output.

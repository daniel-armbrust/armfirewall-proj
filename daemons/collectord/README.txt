ArmFirewall Collection Daemon
=============================

collectord is the persistent operating-system state collection daemon used by
ArmFirewall.

It runs lightweight collectors on their own intervals and stores structured
snapshots in SQLite databases for the web interface to read. The GUI should read
these persisted snapshots instead of running operating-system commands directly.

collectord is separate from monitord. monitord stores time-series monitoring
data in RRD files and generates graphs. collectord stores current operational
state and command diagnostics in SQLite.

The daemon is started by supervisord as a Python package:

    python -m daemons.collectord

Current Scope
-------------

The initial collector set only gathers BIRD diagnostic data.

The BIRD collector runs:

    /usr/sbin/birdcl show protocols

It stores the command execution in diagnostic_command_run and the parsed
protocol rows in diagnostic_protocol inside db/bird.db. The Routing Protocols
GUI reads these tables to render the Diagnostics panel.

Execution Flow
--------------

1. supervisord starts armfirewall-collectord.
2. collectord builds the registered collector list.
3. Each collector runs only when its own interval is due.
4. Collector failures are logged and isolated from the main daemon loop.
5. BIRD diagnostic command output is stored in bird.db.
6. The GUI reads bird.db through the web API.

Files
-----

__init__.py
    Marks this directory as the daemons.collectord Python package.

__main__.py
    Package entry point used by "python -m daemons.collectord".

collectord.py
    Main daemon process, collector registration, scheduler loop and error
    isolation between collectors.

constants.py
    Shared scheduler settings, BIRD command settings, command timeout,
    retention limit, database path and daemon log source.

models.py
    Shared typing contracts used by the daemon, including the collector
    protocol.

collectors/__init__.py
    Marks the collectors directory as a Python package.

collectors/bird.py
    BIRD diagnostics collector. It runs birdcl show protocols, stores raw
    command output, parses protocol rows, and prunes old command history.

Responsibility Boundary
-----------------------

collectord collects read-only operating-system and daemon state for the GUI.
It should not apply configuration changes, start or stop services, or render
configuration files.

Configuration rendering belongs to one-shot work request executors such as
daemons.bird. Service start, stop and restart actions belong to the service
management executor and supervisord.

ArmFirewall Monitoring Daemon
=============================

monitord is the persistent monitoring daemon used by ArmFirewall.

It runs the collector modules in this directory, stores time-series data under
rrd/, and generates graph images under rrd/img for the web interface.

The daemon is started by supervisord as a Python package:

    python -m daemons.monitord

Shared monitoring paths and scheduler settings live in constants.py. Runtime
setup helpers, such as RRD directory creation and rrdtool discovery, live in
runtime.py.

Each monitoring collector lives in its own directory and follows the same
layout:

    <collector>/<collector>.py
        Collector logic, procfs parsing and RRD updates.

    <collector>/constants.py
        Collector-specific interval, paths, data source names, log source and
        graph color settings.

    <collector>/models.py
        Collector-specific dataclasses used by the parser and RRD updater.

    <collector>/graphs.py
        Optional graph generation helpers when one collector produces multiple
        graph families.

Files
-----

__init__.py
    Marks this directory as the daemons.monitord Python package.

__main__.py
    Package entry point used by "python -m daemons.monitord".

monitord.py
    Main daemon process, collector registration, collection loop and error
    isolation between monitoring modules.

constants.py
    Shared paths, scheduler tick setting and main daemon log source used by the
    monitoring daemon.

models.py
    Shared typing contracts used by the daemon, including the collector
    protocol.

runtime.py
    Runtime setup helpers, including rrdtool discovery and RRD directory
    creation.

periods.py
    Shared graph period definitions for Daily, Weekly, Monthly and Yearly
    images.

rrd.py
    Shared RRD helper functions for schema inspection, stale file replacement,
    label escaping and filesystem-safe RRD names.

iface/iface.py
    Collects network interface counters from /proc/net/dev for interfaces
    stored in iface.db.

iface/graphs.py
    Generates traffic, packet and error graphs for monitored interfaces.

iface/constants.py
    Interface collector constants.

iface/models.py
    Interface counter and snapshot data classes.

latency/latency.py
    Collects latency, packet loss and response-time data from configured ping
    targets stored in latency.db.

latency/graphs.py
    Generates latency and packet loss graphs for configured ping targets.

latency/constants.py
    Latency collector constants.

latency/models.py
    Latency target and ping result data classes.

kern/kern.py
    Collects kernel and CPU metrics from /proc and related kernel counters.

kern/graphs.py
    Generates CPU, context switch and kernel usage graphs.

kern/constants.py
    Kernel collector constants.

kern/models.py
    Kernel raw and normalized counter data classes.

loadavg/loadavg.py
    Collects system load averages from /proc/loadavg.

loadavg/constants.py
    Load average collector constants.

loadavg/models.py
    Load average counter data class.

entropy/entropy.py
    Collects kernel entropy availability from /proc/sys/kernel/random.

entropy/constants.py
    Entropy collector constants.

entropy/models.py
    Entropy counter data class.

uptime/uptime.py
    Collects system uptime from /proc/uptime.

uptime/constants.py
    Uptime collector constants.

uptime/models.py
    Uptime counter data class.

mem/mem.py
    Collects memory usage metrics from /proc/meminfo.

mem/constants.py
    Memory collector constants.

mem/models.py
    Memory counter data class.

procstatus/procstatus.py
    Collects process state counters from /proc/<pid>/status.

procstatus/constants.py
    Process status collector constants.

procstatus/models.py
    Process counter data class.

fs/fs.py
    Collects filesystem usage, inode usage and disk activity metrics.

fs/graphs.py
    Generates filesystem usage, inode, I/O operation and I/O time graphs.

fs/constants.py
    Filesystem collector constants.

fs/models.py
    Filesystem mount, disk statistics and snapshot data classes.

netstat/netstat.py
    Collects socket state metrics from /proc/net TCP and UDP tables.

netstat/graphs.py
    Generates socket state graphs grouped by TCP and UDP families.

netstat/constants.py
    Socket state collector constants.

netstat/models.py
    Socket counter data classes.

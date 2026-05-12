ArmFirewall Interface Daemon
============================

The interface daemon continuously collects network interface information from
the operating system and persists it in iface.db.

It discovers interfaces through the system network tools, records IPv4 and IPv6
addresses, updates traffic counters, stores link metadata such as MTU, MAC
address, speed and duplex, and collects per-interface /proc network parameters.

Files
-----

ifaced.py
    Main daemon process, collection loop, operating system parsing and SQLite
    persistence logic.

constants.py
    Static daemon settings, collection interval, log source and the list of
    per-interface /proc parameters collected by the daemon.

models.py
    Data classes used to represent interfaces, addresses and traffic counters.

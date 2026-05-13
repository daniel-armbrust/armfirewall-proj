ArmFirewall Firewall Rules Executor
===================================

The firewall rules executor applies ArmFirewall-managed iptables and ip6tables
changes from the SQLite rule databases.

This module is not a persistent daemon. It is a one-shot work request executor
called by workreqd when the web interface queues Filter, NAT or Mangle rule
changes.

The web interface persists firewall rule changes in the IPv4 and IPv6 rule
databases first. This executor loads the requested rule rows, validates the
selected rule table, applies or removes the matching operating system rules,
updates the SQLite applied state, and removes rows that were marked for delete
after successful execution.

Files
-----

__init__.py
    Marks this directory as the daemons.fwrulesd Python package.

fwrulesd.py
    Work request entry point, request normalization, database selection,
    shared iptables rule specification building and execution orchestration.

constants.py
    Rule database paths, table metadata, protected rule tables, selected SQL
    columns and daemon log source.

models.py
    Data class used to represent the decoded firewall work request context.

common.py
    Shared command helper used to select iptables or ip6tables from the work
    request family.

filter.py
    Filter table operations, including chain policies, rule actions, pending
    apply handling and protected rule behavior.

nat.py
    NAT table operations, including NAT target action mapping, target options
    and port handling.

mangle.py
    Mangle table operations, including mangle target action mapping and pending
    apply handling.

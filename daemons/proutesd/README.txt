ArmFirewall Policy Routing Executor
===================================

The policy routing executor applies ArmFirewall-managed Linux policy routing
changes using iproute2.

This module is not a persistent daemon. It is a one-shot work request executor
called by workreqd when the web interface queues route table, route or routing
rule changes.

The web interface persists policy routing changes in policy-routing.db first.
This executor loads the queued rows, updates /etc/iproute2/rt_tables when route
tables are added or removed, applies route and rule changes with the ip command,
updates the SQLite applied state, and removes rows that were marked for delete
after successful execution.

Files
-----

__init__.py
    Marks this directory as the daemons.proutesd Python package.

__main__.py
    Package entry point used by "python -m daemons.proutesd".

proutesd.py
    Work request entry point, argument parsing, policy routing database
    verification and request dispatch.

executor.py
    Work request execution flow that coordinates routing table, route and rule
    operations.

constants.py
    Policy routing database path, rt_tables path, protected base table ids,
    protected rule priorities and log source.

models.py
    Shared type aliases used by the policy routing executor modules.

commons.py
    Shared helpers for iproute2 family selection, payload id normalization and
    optional command argument construction.

tables.py
    Routing table registry operations, including rt_tables file updates,
    protected table checks, applied state updates and delete cleanup.

routes.py
    Route operations, including route row loading, ip route command
    construction, apply, remove, applied state updates and delete cleanup.

rules.py
    Policy routing rule operations, including rule row loading, ip rule command
    construction, apply, remove, applied state updates and delete cleanup.

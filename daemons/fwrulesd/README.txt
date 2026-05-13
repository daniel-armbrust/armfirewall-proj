ArmFirewall Firewall Rules Executor
===================================

fwrulesd is the ArmFirewall one-shot firewall rule executor. It is called by
workreqd whenever the web interface queues a firewall work request.

This component is responsible for applying ArmFirewall-managed Filter, NAT and
Mangle rules to the operating system through iptables and ip6tables. It reads
the requested rule data from the SQLite rule databases, builds the operating
system command, applies or removes the rule, and keeps the database state in
sync after successful execution.

fwrulesd is not a persistent daemon. It runs once per work request and then
exits.

Execution Flow
--------------

1. The web interface persists the rule change in the proper SQLite database.
2. The web interface creates a work request.
3. workreqd dispatches the work request to daemons.fwrulesd.fwrulesd.
4. fwrulesd loads the affected rule rows.
5. fwrulesd applies, changes or removes the operating system rule.
6. Protected rules are reconciled after apply actions.
7. Pending delete rows are removed from SQLite after a successful full apply.

Directory Layout
----------------

__init__.py
    Marks this directory as the daemons.fwrulesd Python package.

fwrulesd.py
    CLI entry point. It parses work request arguments, decodes the payload and
    calls the execution flow.

actions.py
    Work request execution flow. It validates the category, logs execution
    status, applies the requested action and reconciles protected rules.

commands.py
    iptables/ip6tables command builder and executor helpers. It builds common
    rule specifications, appends protocol, address, interface and conntrack
    matches, and applies, removes or flushes operating system rules.

repository.py
    SQLite access layer for firewall work requests. It resolves rule databases,
    loads rule rows, loads protected rules, and removes pending-delete rows
    after successful execution.

constants.py
    Rule database paths, table metadata, selected SQL columns, protected rule
    table lists, supported protocol/action values and daemon log source.

models.py
    Data classes used by the firewall rule executor.

commons.py
    Shared helpers used by the firewall rule modules.

filter/
    Filter-specific logic.

filter/rules.py
    Filter rule persistence and web-facing rule operations.

filter/table.py
    Filter table operating system behavior, including rule action lookup,
    chain policy handling and configured policy enforcement.

nat/
    NAT-specific logic.

nat/rules.py
    NAT rule persistence and web-facing rule operations.

nat/table.py
    NAT table operating system behavior, including target action lookup,
    destination/source translation options, redirect options and port handling.

mangle/
    Mangle-specific logic.

mangle/rules.py
    Mangle rule persistence and web-facing rule operations.

mangle/table.py
    Mangle table operating system behavior, including target action lookup and
    target-specific options such as MARK, CONNMARK, DSCP, TOS and TTL.

Responsibility Boundary
-----------------------

The web layer creates or updates database records and queues work requests.
fwrulesd performs the operating system firewall changes.

Firewall rule execution should stay inside daemons/fwrulesd. Shared generic
helpers may live in core, but iptables/ip6tables behavior belongs here.

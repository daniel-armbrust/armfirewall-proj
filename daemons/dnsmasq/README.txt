ArmFirewall Dnsmasq Executor
============================

The Dnsmasq executor renders the ArmFirewall-managed dnsmasq configuration
from SQLite into conf/dnsmasq.conf.

This module is not the dnsmasq service itself and it is not a persistent
daemon. It is a one-shot work request executor called by workreqd when the web
interface queues a Dnsmasq configuration apply action.

The web interface only persists Dnsmasq settings in dnsmasq.db. This executor
loads those settings, renders the managed configuration file, validates the
generated syntax with dnsmasq, writes conf/dnsmasq.conf atomically, and clears
the pending apply flag after a successful render.

Service start, restart and stop actions are handled separately by the service
management executor through supervisord.

Files
-----

__init__.py
    Marks this directory as the daemons.dnsmasq Python package.

dnsmasq.py
    Work request entry point, request validation, database verification,
    configuration rendering orchestration, atomic file write and pending apply
    cleanup.

constants.py
    Paths and log source used by the Dnsmasq executor, including dnsmasq.db,
    work-requests.db and conf/dnsmasq.conf.

models.py
    Data classes used to represent the decoded Dnsmasq work request context.

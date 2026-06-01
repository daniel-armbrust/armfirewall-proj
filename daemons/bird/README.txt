ArmFirewall BIRD Executor
=========================

The BIRD executor renders the ArmFirewall-managed BIRD configuration from
SQLite into conf/bird.conf.

This module is not the BIRD routing daemon itself and it is not a persistent
collector. It is a one-shot work request executor called by workreqd when the
web interface queues a BIRD configuration apply action.

The web interface persists BIRD global, kernel, device, direct and RIP settings
in bird.db. This executor loads those settings, renders the managed bird.conf
file, and writes it atomically. The BIRD service process is managed separately
by supervisord through the service management flow.

Runtime diagnostics such as birdcl show protocols are collected by
armfirewall-collectord and stored in bird.db for the GUI to read. Diagnostics
collection does not belong to this executor.

Execution Flow
--------------

1. The web interface persists BIRD settings in db/bird.db.
2. The web interface queues a SERVICE_MANAGEMENT.BIRD_CONFIG work request.
3. workreqd dispatches the work request to daemons.bird.bird.
4. The executor validates the work request context.
5. The executor reads persisted settings from bird.db.
6. The executor renders conf/bird.conf from SQLite state.
7. The executor writes conf/bird.conf atomically and exits.

Files
-----

__init__.py
    Marks this directory as the daemons.bird Python package.

bird.py
    Work request entry point, request validation, database verification,
    configuration rendering orchestration and atomic bird.conf write.

constants.py
    Paths and log source used by the BIRD executor, including bird.db,
    work-requests.db and conf/bird.conf.

models.py
    Data classes used to represent the decoded BIRD work request context.

Responsibility Boundary
-----------------------

The web layer validates user input, persists desired BIRD state in bird.db and
queues work requests. daemons.bird renders that desired state into bird.conf.

Starting, stopping and restarting the BIRD service is handled by the service
management executor and supervisord. Periodic operating-system and birdcl data
collection is handled by armfirewall-collectord.

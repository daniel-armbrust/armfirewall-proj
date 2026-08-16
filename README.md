# ArmFirewall

ArmFirewall is a Linux firewall management platform designed to turn a small server or virtual machine into a controlled network security appliance. It combines host bootstrap automation, SQLite-backed configuration, supervised daemons, RRD-based monitoring, and a FastAPI web interface.

The project follows a deliberate safety model: the web interface persists desired changes and creates work requests, while background daemons apply operating system changes in a controlled execution path. This keeps the GUI focused on management and visibility instead of directly mutating firewall, routing, or service state.

## Main Capabilities

- Manage IPv4 and IPv6 firewall filter, NAT, and mangle rules.
- Persist firewall rules, policy routing, kernel runtime parameters, interfaces, users, services, logs, latency targets, and work requests in SQLite.
- Apply firewall and routing state from persisted databases during system startup.
- Configure LAN and WAN interfaces during installation.
- Enable router mode with packet forwarding, forwarding rules, and NAT masquerade when requested.
- Manage Linux kernel network parameters such as forwarding and TCP/IP runtime settings.
- Monitor interfaces, CPU, memory, load average, uptime, entropy, kernel counters, filesystem usage, socket states, process status, and latency probes.
- Generate RRD graphs in Daily, Weekly, Monthly, and Yearly views.
- Provide operational tools for Ping, MTR, Traceroute, and Packet Capture.
- Manage ArmFirewall services and optional services through supervised work requests.

## Architecture

ArmFirewall is organized by responsibility:

- `web/main.py` starts the FastAPI application, middleware, templates, static files, and route modules.
- `web/routes/` composes the route groups used by the GUI.
- `web/<module>/api.py` contains HTTP API endpoints for a web module.
- `web/<module>/views.py` contains page rendering for a web module.
- `web/workrequests/` provides the shared web APIs and views for queued work requests.
- `core/` contains reusable project helpers for SQLite, processes, interfaces, CPU, memory, disk, logging, constants, payload handling, and supervisord access.
- `daemons/` contains persistent daemons and one-shot executors used by work requests.
- `bin/install.sh` prepares a host for ArmFirewall.
- `bin/armfwinit.sh` reapplies persisted runtime state before supervisord starts the main services.
- `bin/scripts/install/` contains installation-time shell helpers.
- `bin/scripts/startpre/` contains startup pre-flight scripts used by `armfwinit.sh`.
- `db/ddl/` contains versioned SQLite schemas.
- `rrd/` stores generated RRD databases and graph images at runtime.
- `conf/` stores local runtime configuration files generated on the installed host.

## Daemons

ArmFirewall keeps the main runtime services under `supervisord`:

- `armfirewall-api`: runs the FastAPI web application.
- `armfirewall-monitord`: runs monitoring collectors and generates RRD graphs.
- `armfirewall-workreqd`: processes queued work requests.

Additional daemon modules are used as work request executors or service managers:

- `daemons/fwrulesd/`: applies persisted firewall filter, NAT, and mangle changes.
- `daemons/proutesd/`: applies persisted policy routing tables, routes, and rules.
- `daemons/svcmgmtd/`: installs, removes, starts, stops, restarts, and syncs service status.
- `daemons/dnsmasq/`: renders and validates `dnsmasq` configuration from SQLite.
- `daemons/linkfailoverd/`: manages link failover checks and events.

## Services

Services are tracked through `services.db`. The web interface reads the service catalog and runtime state from SQLite, while `svcmgmtd` synchronizes runtime status from supervisord and executes service-related work requests.

Main services are installed with ArmFirewall:

- `armfirewall-api`
- `armfirewall-monitord`
- `armfirewall-workreqd`

Optional services can be installed from the GUI:

- `dnsmasq`
- `squid`
- `bird`

## Work Requests

Most operations that change the operating system are queued as work requests:

1. The web GUI validates and persists the requested configuration.
2. The web GUI creates a work request in `work-requests.db`.
3. `armfirewall-workreqd` picks up the request.
4. The appropriate daemon executor applies the change.
5. Request status and details are updated for the GUI.

This model is used for firewall changes, policy routing, service actions, optional service installation, Dnsmasq configuration, and other controlled system operations.

## Firewall And Routing

Firewall rules are stored by family and table:

- `ipv4-filter-rules.db`
- `ipv4-nat-rules.db`
- `ipv4-mangle-rules.db`
- `ipv6-filter-rules.db`
- `ipv6-nat-rules.db`
- `ipv6-mangle-rules.db`

Startup scripts flush runtime firewall state and reapply the persisted configuration. Filter chain policies, protected rules, NAT rules, mangle rules, conntrack rules, and router mode behavior are represented in the databases and applied by the startup and daemon execution paths.

Policy routing uses Linux `iproute2` and persists route table, route, and rule metadata in `policy-routing.db`.

## Monitoring

`armfirewall-monitord` runs independent collectors under `daemons/monitord/`. Each collector owns its own constants, models, RRD definitions, collection interval, and graph generation when applicable.

Current monitoring areas include:

- Interface traffic and errors.
- CPU and memory.
- Load average.
- Process status.
- Uptime.
- Entropy.
- Kernel counters.
- Filesystem usage and I/O.
- Socket states.
- Latency targets from `latency.db`.

Generated graphs are stored under `rrd/img` and are not versioned.

## Database Schemas

SQLite schemas are versioned in `db/ddl/` and applied during installation. Runtime database files are generated locally and should not be committed.

Current schemas include:

- `dnsmasq.ddl`
- `iface.ddl`
- `ipv4-filter-rules.ddl`
- `ipv4-mangle-rules.ddl`
- `ipv4-nat-rules.ddl`
- `ipv6-filter-rules.ddl`
- `ipv6-mangle-rules.ddl`
- `ipv6-nat-rules.ddl`
- `latency.ddl`
- `linkfailover.ddl`
- `logs.ddl`
- `policy-routing.ddl`
- `proc.ddl`
- `services.ddl`
- `users.ddl`
- `work-requests.ddl`

## Installation

Run the installer as root:

```bash
bin/install.sh --lan-iface <iface>
```

To also register a WAN interface:

```bash
bin/install.sh --lan-iface <lan-iface> --wan-iface <wan-iface>
```

To enable router mode:

```bash
bin/install.sh --lan-iface <lan-iface> --wan-iface <wan-iface> --router-mode
```

Router mode requires `--wan-iface`. Providing only `--wan-iface` registers the WAN interface without enabling forwarding or NAT.

The installer prepares operating system dependencies, disables conflicting firewall services, applies DDLs, creates the admin user, persists selected interfaces, imports route tables, creates the runtime OS user, generates TLS files, writes supervisord configuration, and enables the systemd unit.

## Runtime Data

The following data is generated on the installed system and should remain outside version control:

- SQLite runtime databases and journal files.
- RRD databases and graph images.
- Logs.
- Python virtual environments.
- Local TLS keys and certificates.
- Generated `dnsmasq.conf` and `supervisord.conf`.
- Host-specific captures, dumps, and command output files.

## Development Notes

- Python dependencies are listed in `requirements.txt`.
- Web JavaScript is plain browser JavaScript.
- DDL files are versioned and represent the database schema source of truth.
- Web modules should not execute operating system commands directly; shared system logic belongs in `core/` or the appropriate daemon.
- Work that mutates system state should normally be performed through work requests.

## Author

ArmFirewall was created by Daniel Armbrust and is maintained as an open infrastructure project for Linux firewall, routing, services, and monitoring use cases.

## License

ArmFirewall is released under the MIT License. You may use, copy, modify, merge, publish, distribute, sublicense, and sell copies of the software, provided that the original copyright notice and license text are preserved.

## Project Status

ArmFirewall is under active development. Current work focuses on clean responsibility boundaries between the web GUI, reusable core helpers, persistent daemons, service management, firewall execution, routing, monitoring, and Linux appliance installation.

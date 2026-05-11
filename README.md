![ArmFirewall Logo](./armfirewall.png)

# ArmFirewall

ArmFirewall is a Linux firewall management platform designed to turn a small server or virtual machine into a controlled network security appliance. The project combines operating system automation, persistent configuration in SQLite, background daemons, RRD-based monitoring, and a responsive FastAPI web interface.

The application focuses on predictable firewall operation: baseline protected rules are maintained by the bootstrap process, user-defined firewall and routing changes are persisted in databases, and operational changes are applied through controlled work requests instead of being executed directly from the web interface.

## Main Capabilities

- Manage IPv4 and IPv6 firewall rules for filter, NAT, and mangle tables.
- Persist firewall rules, NAT rules, mangle rules, policy routing, interface inventory, latency targets, work requests, and logs in SQLite databases.
- Bootstrap the host with required operating system packages, database schemas, firewall defaults, policy routing data, and supervisor-managed services.
- Disable conflicting operating system firewall services before applying ArmFirewall-controlled iptables and ip6tables rules.
- Configure LAN and WAN interfaces, enable WAN DHCP, maintain a single default route, and apply masquerading for LAN-to-WAN forwarding.
- Monitor system, network, filesystem, socket state, and latency metrics using RRD files and generated PNG graphs.
- Provide a responsive web GUI with dashboard, network, firewall, monitoring, services, and tools sections.
- Process queued operating system changes through the persistent `workreqd` daemon.

## Architecture

ArmFirewall is organized around clear responsibility boundaries:

- `main.py` initializes the FastAPI application, middleware, static files, and route modules.
- `web/` contains the web GUI, templates, static assets, views, APIs, and HTTP route composition.
- `core/` contains shared helpers such as SQLite access, interface helpers, and logging.
- `bin/armfw.sh` is the main bootstrap/startup script.
- `bin/scripts/` contains operating system automation for dependencies, DDL execution, firewall rules, policy routing, latency defaults, and shell logging.
- `daemons/` contains background and task-execution processes.
- `daemons/monitord/` contains the monitoring collectors responsible for RRD updates and graph generation.
- `db/ddl/` contains the versioned SQLite schemas.
- `rrd/` stores runtime RRD databases and generated graph images.
- `conf/` stores local runtime configuration files.

## Persistent Daemons

The project uses `supervisord` to keep long-running services under control:

- `armfirewall-api`: runs the FastAPI web application.
- `armfirewall-ifaced`: collects network interface inventory and counters into SQLite.
- `armfirewall-monitord`: runs monitoring collectors and generates RRD graphs.
- `armfirewall-workreqd`: processes queued work requests and dispatches operating system actions.

Supervisor log rotation is configured for each managed process.

## Firewall And Routing Model

The firewall model separates runtime operating system state from persistent configuration:

- Protected bootstrap rules are created and verified by startup scripts.
- User-defined rules are stored in the matching SQLite database.
- Applying changes from the GUI creates work requests.
- Work request handlers apply changes to the operating system and update request status.

Policy routing is managed with Linux `iproute2`, including routing table registration in `/etc/iproute2/rt_tables` and persisted route/rule metadata in `db/policy-routing.db`.

## Monitoring Model

Monitoring collectors use Linux `/proc`, system commands, SQLite configuration, and RRDTool:

- Interface traffic and errors.
- CPU, load average, memory, process states, uptime, entropy, and kernel counters.
- Filesystem usage and I/O.
- Socket states.
- Latency targets configured in `db/latency.db`.

Generated graphs are written under `rrd/img` in Daily, Weekly, Monthly, and Yearly variants.

## Database Schemas

SQLite database schemas are kept in `db/ddl/` and applied by `bin/scripts/execddl.sh`. Runtime `.db`, `.wal`, and `.shm` files are generated locally and should not be versioned.

Important schemas include:

- `iface.ddl`
- `latency.ddl`
- `policy-routing.ddl`
- `work-requests.ddl`
- `logs.ddl`
- `ipv4-firewall-rules.ddl`
- `ipv6-firewall-rules.ddl`
- `ipv4-nat-rules.ddl`
- `ipv6-nat-rules.ddl`
- `ipv4-mangle-rules.ddl`
- `ipv6-mangle-rules.ddl`

## Startup

Run the main bootstrap script as root:

```bash
bin/armfw.sh
```

The script installs dependencies, applies DDLs, collects interface choices, configures routing, applies baseline firewall rules, ensures default latency targets, and starts services through supervisord.

## Development Notes

- Python dependencies are listed in `requirements.txt`.
- JavaScript in the web GUI is plain browser JavaScript.
- Generated runtime data such as SQLite databases, RRD files, graph images, logs, virtual environments, and local configuration files are intentionally excluded from version control.
- DDL files are versioned and represent the source of truth for database structure.

## Author

ArmFirewall was created by Daniel Armbrust and is maintained as an open infrastructure project for Linux firewall, routing, and monitoring use cases.

## License

ArmFirewall is released under the MIT License. You may use, copy, modify, merge, publish, distribute, sublicense, and sell copies of the software, provided that the original copyright notice and license text are preserved.

## Project Status

ArmFirewall is under active development. Current work focuses on firewall rule management, policy routing, monitoring, latency probes, and the web GUI needed to operate those functions from a compact network appliance interface.

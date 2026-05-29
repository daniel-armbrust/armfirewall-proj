ArmFirewall Libreswan Executor

libreswand is a one-shot work request executor used by workreqd.

The Web GUI persists Libreswan tunnel definitions in db/libreswan.db and queues
a SERVICE_MANAGEMENT.LIBRESWAN_CONFIG work request. workreqd invokes this module
to render the managed configuration files under conf/libreswan/ and ask
Libreswan to load the enabled tunnels.

Generated files

- conf/libreswan/ipsec.conf
  Main managed Libreswan configuration. It contains config setup and includes
  one per-connection ipsec.conf file.

- conf/libreswan/<connection-name>/ipsec.conf
  Per-connection managed Libreswan tunnel configuration.

- conf/libreswan/ipsec.secrets
  Managed pre-shared secrets used by all enabled connections.

Files

- libreswand.py
  Main executor. It reads libreswan.db, writes configuration files, and runs
  supported Libreswan activation commands.

- constants.py
  Paths and runtime constants used by the executor.

- models.py
  Dataclasses for decoded work requests and persisted tunnel definitions.

- __main__.py
  Allows the executor to run with python -m daemons.libreswand.

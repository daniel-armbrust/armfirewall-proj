"""Operating-system snapshot collector."""
from __future__ import annotations

from pathlib import Path

from core import db, system
from core.constants import SYSTEM_DB_PATH


class SystemCollector:
    """Collect CPU, memory, disk, and process state into system.db."""
    name = "system"
    interval_seconds = 5

    def is_available(self) -> bool:
        return Path("/proc/stat").exists()

    def collect(self) -> None:
        value = system.read_system_status()
        memory, disk = value["memory"], value["root_disk"]
        with db.transaction(SYSTEM_DB_PATH) as conn:
            db.execute_on(conn, """INSERT INTO system_snapshot (
                id, hostname, cpu_model, cpu_count, cpu_usage_percent, architecture, platform, os_name,
                memory_total_bytes, memory_used_bytes, memory_available_bytes, process_count,
                root_disk_total_bytes, root_disk_used_bytes, root_disk_free_bytes, collected_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET hostname=excluded.hostname, cpu_model=excluded.cpu_model,
                cpu_count=excluded.cpu_count, cpu_usage_percent=excluded.cpu_usage_percent,
                architecture=excluded.architecture, platform=excluded.platform, os_name=excluded.os_name,
                memory_total_bytes=excluded.memory_total_bytes, memory_used_bytes=excluded.memory_used_bytes,
                memory_available_bytes=excluded.memory_available_bytes, process_count=excluded.process_count,
                root_disk_total_bytes=excluded.root_disk_total_bytes, root_disk_used_bytes=excluded.root_disk_used_bytes,
                root_disk_free_bytes=excluded.root_disk_free_bytes, collected_at=CURRENT_TIMESTAMP
            """, (system.get_hostname(), value["cpu_model"], value["cpu_count"], value["cpu_usage_percent"],
                  value["architecture"], value["platform"], value["os"], memory["total_bytes"],
                  memory["used_bytes"], memory["available_bytes"], value["process_count"],
                  disk["total_bytes"], disk["used_bytes"], disk["free_bytes"]))

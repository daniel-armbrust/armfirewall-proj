from __future__ import annotations

from web.services.routingprotocols.common import *  # noqa: F403


def normalize_global_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate GUI payload for BIRD global settings."""
    kernel = payload.get("kernel") if isinstance(payload.get("kernel"), dict) else payload
    device = payload.get("device") if isinstance(payload.get("device"), dict) else payload
    direct = payload.get("direct") if isinstance(payload.get("direct"), dict) else payload

    return {
        "router_id": router_id_setting(payload.get("router_id")),
        "hostname": hostname_setting(payload.get("hostname")),
        "debug_enabled": bool_setting(payload.get("debug_enabled", False)),
        "log_syslog": bool_setting(payload.get("log_syslog", True)),
        "kernel": {
            "enabled": bool_setting(kernel.get("kernel_enabled", kernel.get("enabled", True))),
            "route_table": int_setting(kernel.get("kernel_route_table", kernel.get("route_table")), default=254, minimum=1, maximum=4294967295, field="route_table"),
            "learn": "all" if str(kernel.get("kernel_learn", kernel.get("learn", ""))).strip().lower() == "all" else None,
            "channel_family": channel_family_setting(kernel.get("kernel_channel_family", kernel.get("channel_family"))),
            "channel_table_name": optional_text(kernel.get("kernel_channel_table_name", kernel.get("channel_table_name"))) or BIRD_DEFAULT_CHANNEL_TABLE_NAME,
            "import_policy": import_export_setting(kernel.get("kernel_import_policy", kernel.get("import_policy")), field="import_policy", default="all"),
            "export_policy": import_export_setting(kernel.get("kernel_export_policy", kernel.get("export_policy")), field="export_policy", default="none"),
            "metric": int_setting(kernel.get("kernel_metric", kernel.get("metric")), default=32, minimum=0, maximum=4294967295, field="metric"),
            "scan_time_secs": int_setting(kernel.get("kernel_scan_time_secs", kernel.get("scan_time_secs")), default=10, minimum=1, maximum=86400, field="scan_time_secs"),
            "persist": bool_setting(kernel.get("kernel_persist", kernel.get("persist", True))),
        },
        "device": {
            "enabled": bool_setting(device.get("device_enabled", device.get("enabled", True))),
            "scan_time_secs": int_setting(device.get("device_scan_time_secs", device.get("scan_time_secs")), default=10, minimum=1, maximum=86400, field="device_scan_time_secs"),
            "iface_name": iface_name_setting(device.get("device_iface_name", device.get("iface_name"))),
        },
        "direct": {
            "enabled": bool_setting(direct.get("direct_enabled", direct.get("enabled", True))),
            "iface_name": iface_name_setting(direct.get("direct_iface_name", direct.get("iface_name"))),
        },
    }

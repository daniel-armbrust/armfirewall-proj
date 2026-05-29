"""Constants used by the firewall rule work request executor."""

from __future__ import annotations

from core.constants import DB_DIR


LOG_SOURCE = "fwrulesd/fwrulesd.py"

RULE_DATABASES = {
    ("FIREWALL_RULES", "IPV4"): DB_DIR / "ipv4-filter-rules.db",
    ("FIREWALL_RULES", "IPV6"): DB_DIR / "ipv6-filter-rules.db",
    ("NAT_RULES", "IPV4"): DB_DIR / "ipv4-nat-rules.db",
    ("NAT_RULES", "IPV6"): DB_DIR / "ipv6-nat-rules.db",
    ("MANGLE_RULES", "IPV4"): DB_DIR / "ipv4-mangle-rules.db",
    ("MANGLE_RULES", "IPV6"): DB_DIR / "ipv6-mangle-rules.db",
}

TABLE_METADATA = {
    "filter_input_rules": ("filter", "INPUT"),
    "filter_forward_rules": ("filter", "FORWARD"),
    "filter_output_rules": ("filter", "OUTPUT"),
    "nat_prerouting_rules": ("nat", "PREROUTING"),
    "nat_input_rules": ("nat", "INPUT"),
    "nat_output_rules": ("nat", "OUTPUT"),
    "nat_postrouting_rules": ("nat", "POSTROUTING"),
    "mangle_prerouting_rules": ("mangle", "PREROUTING"),
    "mangle_input_rules": ("mangle", "INPUT"),
    "mangle_forward_rules": ("mangle", "FORWARD"),
    "mangle_output_rules": ("mangle", "OUTPUT"),
    "mangle_postrouting_rules": ("mangle", "POSTROUTING"),
}

SELECT_COLUMNS = {
    "filter_input_rules": """
        id, rule_order, iface_in, '' AS iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        action, protected, enabled, created_at, updated_at
    """,
    "filter_forward_rules": """
        id, rule_order, iface_in, iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        action, protected, enabled, created_at, updated_at
    """,
    "filter_output_rules": """
        id, rule_order, '' AS iface_in, iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        action, protected, enabled, created_at, updated_at
    """,
    "nat_prerouting_rules": """
        id, rule_order, iface_in, '' AS iface_out,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        nat_action, to_addr, to_port,
        protected, enabled, created_at, updated_at
    """,
    "nat_input_rules": """
        id, rule_order, iface_in, '' AS iface_out,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        nat_action, to_addr, to_port,
        protected, enabled, created_at, updated_at
    """,
    "nat_output_rules": """
        id, rule_order, '' AS iface_in, iface_out,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        nat_action, to_addr, to_port,
        protected, enabled, created_at, updated_at
    """,
    "nat_postrouting_rules": """
        id, rule_order, '' AS iface_in, iface_out,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        nat_action, to_addr, to_port,
        protected, enabled, created_at, updated_at
    """,
    "mangle_prerouting_rules": """
        id, rule_order, iface_in, '' AS iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        mangle_action, mark_value, dscp_value, tos_value, ttl_value,
        protected, enabled, created_at, updated_at
    """,
    "mangle_input_rules": """
        id, rule_order, iface_in, '' AS iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        mangle_action, mark_value, dscp_value, tos_value, ttl_value,
        protected, enabled, created_at, updated_at
    """,
    "mangle_forward_rules": """
        id, rule_order, iface_in, iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        mangle_action, mark_value, dscp_value, tos_value, ttl_value,
        protected, enabled, created_at, updated_at
    """,
    "mangle_output_rules": """
        id, rule_order, '' AS iface_in, iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        mangle_action, mark_value, dscp_value, tos_value, ttl_value,
        protected, enabled, created_at, updated_at
    """,
    "mangle_postrouting_rules": """
        id, rule_order, '' AS iface_in, iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        mangle_action, mark_value, dscp_value, tos_value, ttl_value,
        protected, enabled, created_at, updated_at
    """,
}

WILDCARD_ADDRESSES = {"0.0.0.0/0", "::/0", "", None}

FAMILY_PROTOCOLS = {
    "IPV4": {"all", "tcp", "udp", "icmp"},
    "IPV6": {"all", "tcp", "udp", "icmpv6"},
}

FILTER_POLICY_CHAINS = ("INPUT", "FORWARD")

FILTER_BUILTIN_CHAINS = ("INPUT", "FORWARD", "OUTPUT")

DEFAULT_FILTER_POLICIES = {
    "INPUT": "DROP",
    "FORWARD": "DROP",
    "OUTPUT": "ACCEPT",
}

FILTER_DEFAULT_POLICIES = DEFAULT_FILTER_POLICIES

FILTER_POLICIES = {"ACCEPT", "DROP"}

FILTER_ACTIONS = {"ACCEPT", "DROP", "REJECT"}

FILTER_FAMILY_DATABASES = {
    "IPV4": RULE_DATABASES[("FIREWALL_RULES", "IPV4")],
    "IPV6": RULE_DATABASES[("FIREWALL_RULES", "IPV6")],
}

FILTER_CHAIN_TABLES = {
    "INPUT": "filter_input_rules",
    "FORWARD": "filter_forward_rules",
    "OUTPUT": "filter_output_rules",
}

FILTER_RULE_TABLES = ("filter_input_rules", "filter_forward_rules", "filter_output_rules")

NAT_FAMILY_DATABASES = {
    "IPV4": RULE_DATABASES[("NAT_RULES", "IPV4")],
    "IPV6": RULE_DATABASES[("NAT_RULES", "IPV6")],
}

NAT_CHAIN_TABLES = {
    "PREROUTING": "nat_prerouting_rules",
    "INPUT": "nat_input_rules",
    "OUTPUT": "nat_output_rules",
    "POSTROUTING": "nat_postrouting_rules",
}

NAT_CHAIN_ACTIONS = {
    "PREROUTING": {"DNAT", "REDIRECT", "ACCEPT", "RETURN"},
    "INPUT": {"DNAT", "REDIRECT", "ACCEPT", "RETURN"},
    "OUTPUT": {"DNAT", "REDIRECT", "ACCEPT", "RETURN"},
    "POSTROUTING": {"SNAT", "MASQUERADE", "ACCEPT", "RETURN"},
}

MANGLE_FAMILY_DATABASES = {
    "IPV4": RULE_DATABASES[("MANGLE_RULES", "IPV4")],
    "IPV6": RULE_DATABASES[("MANGLE_RULES", "IPV6")],
}

MANGLE_CHAIN_TABLES = {
    "PREROUTING": "mangle_prerouting_rules",
    "INPUT": "mangle_input_rules",
    "FORWARD": "mangle_forward_rules",
    "OUTPUT": "mangle_output_rules",
    "POSTROUTING": "mangle_postrouting_rules",
}

MANGLE_ACTIONS = {"MARK", "CONNMARK", "DSCP", "TOS", "TTL", "ACCEPT", "DROP", "RETURN"}

PROTECTED_RULE_TABLES = {
    "FIREWALL_RULES": FILTER_RULE_TABLES,
    "NAT_RULES": ("nat_prerouting_rules", "nat_input_rules", "nat_output_rules", "nat_postrouting_rules"),
    "MANGLE_RULES": (
        "mangle_prerouting_rules",
        "mangle_input_rules",
        "mangle_forward_rules",
        "mangle_output_rules",
        "mangle_postrouting_rules",
    ),
}

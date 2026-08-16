"""Regular-expression patterns and vocabulary for firewall command extraction."""

from __future__ import annotations

import re


# Matches a numeric port followed by a slash-delimited protocol, such as 22/TCP.
PORT_WITH_PROTOCOL_PATTERN = re.compile(
    r"\b(?:port\s+)?(?P<port>\d{1,5})\s*/\s*(?P<protocol>tcp|udp|icmp)\b",
    re.IGNORECASE,
)

# Matches a numeric port explicitly introduced by the word "port".
PORT_PATTERN = re.compile(r"\bport\s+(?P<port>\d{1,5})\b", re.IGNORECASE)

# Matches a numeric port in the "is open" context of a firewall-rule check.
CHECK_OPEN_NUMERIC_PORT_PATTERN = re.compile(
    r"\b(?P<port>\d{1,5})\s+is\s+open\b",
    re.IGNORECASE,
)

# Defines an IPv4 address with an optional CIDR network prefix.
IP_PATTERN = r"(?:(?:\d{1,3}\.){3}\d{1,3})(?:/\d{1,2})?"

# Matches an IPv4 source introduced by "from" or "source".
SOURCE_PATTERN = re.compile(
    rf"\b(?:from|source)\s+(?:ip\s+)?(?P<value>{IP_PATTERN})\b",
    re.IGNORECASE,
)

# Matches an IPv4 destination introduced by "to" or "destination".
DESTINATION_PATTERN = re.compile(
    rf"\b(?:to|destination)\s+(?:ip\s+)?(?P<value>{IP_PATTERN})\b",
    re.IGNORECASE,
)

# Matches an interface name introduced by "via", "through", or "on interface".
INTERFACE_PATTERN = re.compile(
    r"\b(?:(?:via|through)\s+(?:interface\s+)?|on\s+interface\s+)"
    r"(?P<value>[a-z][a-z0-9_.-]*)\b",
    re.IGNORECASE,
)

# Lists contextual words that must not be returned as interface names.
IGNORED_INTERFACE_VALUES = frozenset({"firewall", "the"})

# Lists protocols recognized by the basic firewall extractor.
PROTOCOLS = frozenset({"tcp", "udp", "icmp"})

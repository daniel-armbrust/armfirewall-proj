"""spaCy-backed extractors for basic firewall command entities."""

from __future__ import annotations

import ipaddress
from functools import lru_cache

import spacy
from spacy.language import Language
from spacy.matcher import Matcher
from spacy.tokens import Doc
from word2number import w2n

from core.constants import ADAM_SPOKEN_PORT_MAX_TOKENS

from .patterns import (
    CHECK_OPEN_NUMERIC_PORT_PATTERN,
    DESTINATION_PATTERN,
    IGNORED_INTERFACE_VALUES,
    INTERFACE_PATTERN,
    PORT_PATTERN,
    PORT_WITH_PROTOCOL_PATTERN,
    PROTOCOLS,
    SOURCE_PATTERN,
)


@lru_cache(maxsize=1)
def _language() -> Language:
    """Load the lightweight English tokenizer without a downloaded language model."""
    return spacy.blank("en")


@lru_cache(maxsize=1)
def _protocol_matcher() -> Matcher:
    """Build the spaCy matcher used to recognize standalone protocols."""
    matcher = Matcher(_language().vocab)
    matcher.add(
        "PROTOCOL",
        [[{"LOWER": {"IN": sorted(PROTOCOLS)}}]],
    )
    return matcher


def _valid_port(value: str) -> int | None:
    """Return a valid TCP/UDP port number or no value."""
    port = int(value)
    return port if 1 <= port <= 65535 else None


def _spoken_port(tokens: list[str], *, suffix: bool) -> int | None:
    """Convert a contiguous spoken-number token sequence to a valid port."""
    values = tokens[-ADAM_SPOKEN_PORT_MAX_TOKENS:]
    offsets = range(len(values)) if suffix else range(0, 1)
    for offset in offsets:
        candidates = values[offset:] if suffix else values
        for end in range(len(candidates), 0, -1):
            try:
                return _valid_port(str(w2n.word_to_num(" ".join(candidates[:end]))))
            except ValueError:
                continue
    return None


def _explicit_spoken_port(document: Doc) -> int | None:
    """Extract a spoken port following an explicit "port" token."""
    for index, token in enumerate(document):
        if token.lower_ == "port":
            return _spoken_port(
                [item.text for item in document[index + 1:index + 1 + ADAM_SPOKEN_PORT_MAX_TOKENS]],
                suffix=False,
            )
    return None


def _open_rule_spoken_port(document: Doc) -> int | None:
    """Extract a spoken port immediately before the "is open" check context."""
    for index, token in enumerate(document[:-1]):
        if token.lower_ == "is" and document[index + 1].lower_ == "open":
            return _spoken_port(
                [item.text for item in document[max(0, index - ADAM_SPOKEN_PORT_MAX_TOKENS):index]],
                suffix=True,
            )
    return None


def _valid_address(value: str) -> str | None:
    """Return a valid IPv4 address or network string."""
    try:
        if "/" in value:
            return str(ipaddress.ip_network(value, strict=False))
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def extract_firewall_rule_entities(text: str) -> dict[str, str | int]:
    """Extract common fields used by firewall-rule commands."""
    document = _language()(text)
    entities: dict[str, str | int] = {}
    port_match = PORT_WITH_PROTOCOL_PATTERN.search(document.text)

    if port_match is not None:
        port = _valid_port(port_match.group("port"))
        if port is not None:
            entities["port"] = port
        entities["protocol"] = port_match.group("protocol").lower()
    else:
        port_match = PORT_PATTERN.search(document.text)
        if port_match is not None:
            port = _valid_port(port_match.group("port"))
            if port is not None:
                entities["port"] = port
        else:
            port = _explicit_spoken_port(document)
            if port is not None:
                entities["port"] = port
            else:
                contextual_port_match = CHECK_OPEN_NUMERIC_PORT_PATTERN.search(document.text)
                if contextual_port_match is not None:
                    port = _valid_port(contextual_port_match.group("port"))
                    if port is not None:
                        entities["port"] = port
                else:
                    port = _open_rule_spoken_port(document)
                    if port is not None:
                        entities["port"] = port

        protocol_matches = _protocol_matcher()(document)
        if protocol_matches:
            _, start, _ = protocol_matches[0]
            entities["protocol"] = document[start].lower_

    source_match = SOURCE_PATTERN.search(document.text)
    if source_match is not None:
        source = _valid_address(source_match.group("value"))
        if source is not None:
            entities["source"] = source

    destination_match = DESTINATION_PATTERN.search(document.text)
    if destination_match is not None:
        destination = _valid_address(destination_match.group("value"))
        if destination is not None:
            entities["destination"] = destination

    interface_match = INTERFACE_PATTERN.search(document.text)
    if interface_match is not None:
        interface = interface_match.group("value").lower()
        if interface not in IGNORED_INTERFACE_VALUES:
            entities["interface"] = interface

    return entities

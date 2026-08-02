"""Cryptographic hashing helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path


SHA256_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one file."""
    digest = hashlib.sha256()

    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(SHA256_CHUNK_SIZE), b""):
            digest.update(chunk)

    return digest.hexdigest()

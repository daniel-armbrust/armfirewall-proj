"""Module entrypoint for armfirewall-adamd."""

import sys

from .adamd import entrypoint


if __name__ == "__main__":
    sys.exit(entrypoint())

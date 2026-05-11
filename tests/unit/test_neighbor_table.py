from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest import mock

from web.network import neighbor_table


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


class NeighborTableParserTests(unittest.TestCase):
    """Validate parsing for Linux ip neighbor output."""

    def test_address_family_detects_ipv4_and_ipv6(self) -> None:
        """Classify neighbor addresses by address shape."""
        self.assertEqual(neighbor_table.address_family("192.0.2.1"), "ipv4")
        self.assertEqual(neighbor_table.address_family("fe80::200:ff:fe00:1"), "ipv6")

    def test_parse_ipv4_reachable_neighbor(self) -> None:
        """Parse a common IPv4 neighbor with MAC and REACHABLE state."""
        row = neighbor_table.parse_neighbor_line(
            "192.0.2.1 dev eth0 lladdr 02:00:00:00:00:01 REACHABLE"
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["addr_family"], "ipv4")
        self.assertEqual(row["ip_address"], "192.0.2.1")
        self.assertEqual(row["iface"], "eth0")
        self.assertEqual(row["mac_address"], "02:00:00:00:00:01")
        self.assertEqual(row["state"], "REACHABLE")
        self.assertEqual(row["flags"], "-")

    def test_parse_ipv4_failed_without_mac(self) -> None:
        """Parse a failed neighbor entry that has no lladdr token."""
        row = neighbor_table.parse_neighbor_line("198.51.100.10 dev eth1 FAILED")

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["addr_family"], "ipv4")
        self.assertEqual(row["iface"], "eth1")
        self.assertEqual(row["mac_address"], "-")
        self.assertEqual(row["state"], "FAILED")

    def test_parse_ipv6_router_neighbor(self) -> None:
        """Parse an IPv6 neighbor and preserve router metadata."""
        row = neighbor_table.parse_neighbor_line(
            "fe80::200:ff:fe00:1 dev eth0 lladdr 02:00:00:00:00:02 router STALE"
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["addr_family"], "ipv6")
        self.assertEqual(row["state"], "STALE")
        self.assertEqual(row["flags"], "router")

    def test_parse_neighbor_line_ignores_blank_lines(self) -> None:
        """Return None for blank command output lines."""
        self.assertIsNone(neighbor_table.parse_neighbor_line(""))
        self.assertIsNone(neighbor_table.parse_neighbor_line("   "))


class NeighborTableCollectionTests(unittest.TestCase):
    """Validate neighbor table collection summaries."""

    def test_read_ip_neighbors_uses_ip_neighbor_show(self) -> None:
        """Read and parse command output from ip neighbor show."""
        fixture = (FIXTURES_DIR / "ip_neighbor_show.txt").read_text(encoding="utf-8")
        completed = subprocess.CompletedProcess(
            args=["ip", "neighbor", "show"],
            returncode=0,
            stdout=fixture,
            stderr="",
        )

        with mock.patch("web.network.neighbor_table.subprocess.run", return_value=completed) as run_mock:
            rows = neighbor_table.read_ip_neighbors()

        run_mock.assert_called_once_with(
            ["ip", "neighbor", "show"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["source"], "ip-neighbor")

    def test_read_ip_neighbors_raises_command_error(self) -> None:
        """Raise a clear error when ip neighbor show fails."""
        completed = subprocess.CompletedProcess(
            args=["ip", "neighbor", "show"],
            returncode=1,
            stdout="",
            stderr="permission denied",
        )

        with mock.patch("web.network.neighbor_table.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                neighbor_table.read_ip_neighbors()

    def test_get_neighbor_table_builds_summary(self) -> None:
        """Build summary counters from parsed neighbor entries."""
        rows = [
            neighbor_table.parse_neighbor_line("192.0.2.1 dev eth0 lladdr 02:00:00:00:00:01 REACHABLE"),
            neighbor_table.parse_neighbor_line("198.51.100.10 dev eth1 FAILED"),
            neighbor_table.parse_neighbor_line(
                "fe80::200:ff:fe00:1 dev eth0 lladdr 02:00:00:00:00:02 router STALE"
            ),
        ]

        with mock.patch("web.network.neighbor_table.read_ip_neighbors", return_value=[row for row in rows if row]):
            data = neighbor_table.get_neighbor_table()

        self.assertEqual(data["summary"]["entries"], 3)
        self.assertEqual(data["summary"]["interfaces"], 2)
        self.assertEqual(data["summary"]["reachable"], 2)
        self.assertEqual(data["summary"]["ipv4"], 2)
        self.assertEqual(data["summary"]["ipv6"], 1)
        self.assertEqual(data["summary"]["source"], "ip-neighbor")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import subprocess
import unittest
from unittest import mock

from web.network import policy_routing


class PolicyRoutingRuntimeRoutesTests(unittest.TestCase):
    """Validate the read-only kernel route inventory used by the GUI."""

    def test_runtime_route_rows_reads_kernel_state_not_persisted_routes(self) -> None:
        output = json.dumps(
            [
                {
                    "dst": "default",
                    "gateway": "100.64.0.1",
                    "dev": "wan",
                    "protocol": "dhcp",
                    "metric": 101,
                },
                {
                    "dst": "192.168.88.0/24",
                    "dev": "lan2",
                    "protocol": "kernel",
                    "scope": "link",
                    "prefsrc": "192.168.88.1",
                    "table": "main",
                },
                {
                    "dst": "default",
                    "gateway": "192.168.1.254",
                    "dev": "lan1",
                    "table": "azza",
                    "flags": ["onlink"],
                },
            ]
        )
        completed = subprocess.CompletedProcess(
            args=["ip", "-j", "route", "show", "table", "all"],
            returncode=0,
            stdout=output,
            stderr="",
        )
        ipv6_completed = subprocess.CompletedProcess(
            args=["ip", "-j", "-6", "route", "show", "table", "all"],
            returncode=0,
            stdout="[]",
            stderr="",
        )
        tables = [
            {"table_id": 254, "table_name": "main"},
            {"table_id": 100, "table_name": "azza"},
        ]

        with mock.patch(
            "web.network.policy_routing.subprocess.run",
            side_effect=[completed, ipv6_completed],
        ) as run_mock:
            with mock.patch("web.network.policy_routing.Path.read_text", side_effect=OSError):
                rows = policy_routing.runtime_route_rows(tables)

        run_mock.assert_has_calls([
            mock.call(
                ["ip", "-j", "-4", "route", "show", "table", "all"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            ),
            mock.call(
                ["ip", "-j", "-6", "route", "show", "table", "all"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            ),
        ])
        self.assertEqual(run_mock.call_count, 2)
        self.assertEqual(rows[0]["gateway"], "100.64.0.1")
        self.assertEqual(rows[0]["table_id"], 254)
        self.assertEqual(rows[1]["preferred_source"], "192.168.88.1")
        self.assertEqual(rows[2]["table_id"], 100)
        self.assertEqual(rows[2]["onlink"], 1)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["protected"] == 1 for row in rows))

    def test_route_get_uses_an_address_argument_without_a_shell(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["ip", "route", "get", "192.0.2.10"],
            returncode=0,
            stdout="192.0.2.10 via 192.0.2.1 dev wan src 192.0.2.2 uid 0\n    cache\n",
            stderr="",
        )

        with mock.patch("web.network.policy_routing.subprocess.run", return_value=completed) as run_mock:
            result = policy_routing.route_get("192.0.2.10")

        run_mock.assert_called_once_with(
            ["ip", "route", "get", "192.0.2.10"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(result["addr_family"], "ipv4")
        self.assertEqual(result["output"], "192.0.2.10 via 192.0.2.1 dev wan src 192.0.2.2 uid 0\n    cache")


if __name__ == "__main__":
    unittest.main()

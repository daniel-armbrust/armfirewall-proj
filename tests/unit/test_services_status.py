from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from web.routes.services import routes as services_routes
from web.services import api as services_status
from web.workrequests import api as workrequests_api


class SupervisorStatusParserTests(unittest.TestCase):
    """Validate supervisorctl status parsing."""

    def test_parse_running_program(self) -> None:
        """Parse a running supervisor program line."""
        row = services_status.parse_supervisor_status_line(
            "armfirewall-api                  RUNNING   pid 955689, uptime 0:01:21"
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["name"], "armfirewall-api")
        self.assertEqual(row["state"], "RUNNING")
        self.assertEqual(row["pid"], "955689")
        self.assertEqual(row["uptime"], "0:01:21")

    def test_parse_stopped_program(self) -> None:
        """Parse a stopped supervisor program line."""
        row = services_status.parse_supervisor_status_line("armfirewall-workreqd STOPPED Not started")

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["name"], "armfirewall-workreqd")
        self.assertEqual(row["state"], "STOPPED")
        self.assertEqual(row["pid"], "-")
        self.assertEqual(row["details"], "Not started")

    def test_parse_blank_line(self) -> None:
        """Ignore blank supervisorctl output lines."""
        self.assertIsNone(services_status.parse_supervisor_status_line(""))

    def test_expected_service_statuses_marks_missing_services(self) -> None:
        """Mark expected ArmFirewall services that are missing from supervisord."""
        rows = [
            {
                "name": "armfirewall-api",
                "state": "RUNNING",
                "pid": "955689",
                "uptime": "0:01:21",
                "details": "pid 955689, uptime 0:01:21",
            }
        ]

        services = services_status.expected_service_statuses(rows)
        by_name = {service["name"]: service for service in services}

        self.assertTrue(by_name["armfirewall-api"]["installed"])
        self.assertEqual(by_name["armfirewall-api"]["state"], "RUNNING")
        self.assertTrue(by_name["armfirewall-api"]["protected"])
        self.assertNotIn("dnsmasq", by_name)

    def test_protected_service_cannot_be_controlled(self) -> None:
        """Block GUI control actions for protected services."""
        with self.assertRaisesRegex(ValueError, "Protected services"):
            services_status.control_service("armfirewall-api", "stop")

    def test_unknown_service_cannot_be_controlled(self) -> None:
        """Block GUI control actions for unknown services."""
        with self.assertRaisesRegex(ValueError, "Unknown ArmFirewall service"):
            services_status.control_service("sshd", "stop")

    def test_optional_service_statuses_include_squid_proxy(self) -> None:
        """Expose Squid as an optional ArmFirewall service."""
        services = services_status.optional_service_statuses([])
        by_name = {service["name"]: service for service in services}
        self.assertIn("dnsmasq", by_name)
        self.assertIn("squid", by_name)
        self.assertIn("bird", by_name)
        self.assertEqual(by_name["dnsmasq"]["display_name"], "Dnsmasq")
        self.assertEqual(by_name["dnsmasq"]["state"], "NOT INSTALLED")
        self.assertEqual(by_name["squid"]["display_name"], "SQUID Proxy")
        self.assertEqual(by_name["squid"]["state"], "NOT INSTALLED")

    def test_unknown_optional_service_cannot_be_installed(self) -> None:
        """Block install requests for unknown optional services."""
        with self.assertRaisesRegex(ValueError, "Unknown optional ArmFirewall service"):
            services_status.install_optional_service("armfirewall-unknown")

    def test_optional_service_install_is_queued(self) -> None:
        """Queue optional service installation as a work request."""
        original_db_path = workrequests_api.WORK_REQUEST_DB_PATH
        ddl_path = Path(__file__).resolve().parents[2] / "db" / "ddl" / "work-requests.ddl"
        try:
            with TemporaryDirectory() as tmpdir:
                tmp_db_path = Path(tmpdir) / "work-requests.db"
                workrequests_api.WORK_REQUEST_DB_PATH = tmp_db_path
                with workrequests_api.db.transaction(tmp_db_path, require_existing=False) as conn:
                    conn.executescript(ddl_path.read_text(encoding="utf-8"))

                service_request = services_status.install_optional_service("squid")
                result = services_routes.post_service_work_request(service_request)

                self.assertEqual(result["status"], "queue")
                with workrequests_api.db.connection(tmp_db_path) as conn:
                    row = workrequests_api.db.fetch_one_on(
                        conn,
                        """
                        SELECT category_name, action_name, status, payload_json
                        FROM work_requests
                        WHERE id = ?
                        """,
                        (result["work_request_id"],),
                    )
                    self.assertIsNotNone(row)
                    assert row is not None
                    self.assertEqual(row["category_name"], "SERVICE_MANAGEMENT.OPTIONAL_SERVICES")
                    self.assertEqual(row["action_name"], "install")
                    self.assertEqual(row["status"], "queue")
                    self.assertIn("squid", row["payload_json"])
        finally:
            workrequests_api.WORK_REQUEST_DB_PATH = original_db_path

    def test_optional_service_uninstall_is_queued(self) -> None:
        """Queue optional service removal as a work request."""
        original_db_path = workrequests_api.WORK_REQUEST_DB_PATH
        ddl_path = Path(__file__).resolve().parents[2] / "db" / "ddl" / "work-requests.ddl"
        try:
            with TemporaryDirectory() as tmpdir:
                tmp_db_path = Path(tmpdir) / "work-requests.db"
                workrequests_api.WORK_REQUEST_DB_PATH = tmp_db_path
                with workrequests_api.db.transaction(tmp_db_path, require_existing=False) as conn:
                    conn.executescript(ddl_path.read_text(encoding="utf-8"))

                service_request = services_status.uninstall_optional_service("squid")
                result = services_routes.post_service_work_request(service_request)

                self.assertEqual(result["status"], "queue")
                with workrequests_api.db.connection(tmp_db_path) as conn:
                    row = workrequests_api.db.fetch_one_on(
                        conn,
                        """
                        SELECT category_name, action_name, status, payload_json
                        FROM work_requests
                        WHERE id = ?
                        """,
                        (result["work_request_id"],),
                    )
                    self.assertIsNotNone(row)
                    assert row is not None
                    self.assertEqual(row["category_name"], "SERVICE_MANAGEMENT.OPTIONAL_SERVICES")
                    self.assertEqual(row["action_name"], "uninstall")
                    self.assertEqual(row["status"], "queue")
                    self.assertIn("squid", row["payload_json"])
        finally:
            workrequests_api.WORK_REQUEST_DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main()

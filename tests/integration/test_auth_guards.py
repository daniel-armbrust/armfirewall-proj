from __future__ import annotations

import unittest
from types import SimpleNamespace

from web import auth


class AuthenticationGuardTests(unittest.TestCase):
    """Validate authentication guard helpers without starting the web server."""

    def test_public_paths_allow_login_and_static_assets(self) -> None:
        """Allow login flow and static assets without a session."""
        self.assertTrue(auth.is_public_path("/login"))
        self.assertTrue(auth.is_public_path("/login/change-password"))
        self.assertTrue(auth.is_public_path("/static/js/globals.js"))

    def test_private_paths_are_not_public(self) -> None:
        """Require authentication for application pages and APIs."""
        self.assertFalse(auth.is_public_path("/network/neighbor-table"))
        self.assertFalse(auth.is_public_path("/api/network/neighbor-table"))

    def test_wants_json_for_api_paths(self) -> None:
        """Return JSON errors for API paths."""
        request = SimpleNamespace(headers={}, url=SimpleNamespace(path="/api/network/neighbor-table"))
        self.assertTrue(auth.wants_json(request))

    def test_wants_json_for_accept_header(self) -> None:
        """Return JSON errors when the client requests JSON."""
        request = SimpleNamespace(
            headers={"accept": "application/json"},
            url=SimpleNamespace(path="/network/neighbor-table"),
        )
        self.assertTrue(auth.wants_json(request))


if __name__ == "__main__":
    unittest.main()

"""Tests for the ADAM transcription endpoint."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from web.adam.api import api_receive_transcription, router
from web.adam.models import AdamTranscriptionPayload


class AdamTranscriptionApiTests(unittest.TestCase):
    def test_receive_transcription_without_processing(self) -> None:
        payload = AdamTranscriptionPayload(
            text="check if port twenty two is open",
            language="en-US",
        )

        self.assertEqual(api_receive_transcription(payload), {"status": "received"})

    def test_empty_transcription_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            AdamTranscriptionPayload(text="", language="en-US")

    def test_transcription_post_route_is_registered(self) -> None:
        matching_routes = [
            route
            for route in router.routes
            if route.path == "/api/adam/transcription"
        ]

        self.assertEqual(len(matching_routes), 1)
        self.assertIn("POST", matching_routes[0].methods)


if __name__ == "__main__":
    unittest.main()

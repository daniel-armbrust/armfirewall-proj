"""Tests for the ADAM transcription endpoint."""

from __future__ import annotations

import asyncio
from io import BytesIO
import unittest
from unittest.mock import patch

from fastapi import UploadFile

from web.adam.transcription.api import api_transcribe_command
from web.adam.transcription.routes import router


class AdamTranscriptionApiTests(unittest.TestCase):
    def test_transcribes_browser_audio(self) -> None:
        audio = UploadFile(filename="command.wav", file=BytesIO(b"wav-audio"))

        with patch(
            "web.adam.transcription.api.transcribe_command",
            return_value="check if port 22 is open",
        ):
            result = asyncio.run(api_transcribe_command(audio, "en-US"))

        self.assertEqual(result, {"text": "check if port 22 is open"})

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

from __future__ import annotations

import asyncio
import json
import unittest
from collections import deque
from unittest import mock

from core.constants import (
    ADAM_TEXT_CLASSIFIER_IGNORE_CONFIDENCE,
    ADAM_TEXT_CLASSIFIER_MIN_CONFIDENCE,
    ADAM_WEBSOCKET_LOG_SOURCE,
    ADAM_WEBSOCKET_REPEAT_PROMPTS,
)
from web.adam.command_extraction.schemas import CommandExtraction
from web.adam.text_classification.inference import IntentPrediction
from web.adam.websocket import commands


class FakeWebSocket:
    def __init__(self, message: dict[str, object]) -> None:
        self.message = message
        self.events: list[dict[str, object]] = []

    async def receive_text(self) -> str:
        return json.dumps(self.message)

    async def send_json(self, event: dict[str, object]) -> None:
        self.events.append(event)


class AdamWebSocketCommandTests(unittest.TestCase):
    def _message(self) -> dict[str, object]:
        return {
            "type": "command.submit",
            "request_id": "11111111-1111-4111-8111-111111111111",
            "text": "Check port 22/TCP from 10.0.0.5.",
            "language": "en-US",
        }

    def test_extracts_a_high_confidence_supported_command(self) -> None:
        channel = FakeWebSocket(self._message())

        with (
            mock.patch.object(
                commands,
                "infer_intent",
                return_value=IntentPrediction(
                    "check_firewall_rule",
                    ADAM_TEXT_CLASSIFIER_MIN_CONFIDENCE + 0.15,
                ),
            ),
            mock.patch.object(
                commands,
                "extract_command",
                return_value=CommandExtraction(
                    "check_firewall_rule",
                    {"port": 22, "protocol": "tcp", "source": "10.0.0.5"},
                ),
            ),
            mock.patch.object(commands.logger, "log") as log,
        ):
            asyncio.run(commands.receive_command(channel, deque(maxlen=8)))

        log.assert_called_once()
        self.assertEqual(log.call_args.kwargs["source"], ADAM_WEBSOCKET_LOG_SOURCE)
        self.assertIn('"intent": "check_firewall_rule"', log.call_args.args[0])
        self.assertEqual(
            channel.events[-1],
            {
                "type": "command.response",
                "request_id": "11111111-1111-4111-8111-111111111111",
                "status": "extracted",
                "message": "Voice command intent and fields extracted.",
                "language": "en-US",
                "command": {
                    "intent": "check_firewall_rule",
                    "entities": {
                        "port": 22,
                        "protocol": "tcp",
                        "source": "10.0.0.5",
                    },
                },
            },
        )

    def test_requests_a_repeat_for_low_confidence(self) -> None:
        channel = FakeWebSocket(self._message())

        with (
            mock.patch.object(
                commands,
                "infer_intent",
                return_value=IntentPrediction(
                    "check_firewall_rule",
                    ADAM_TEXT_CLASSIFIER_MIN_CONFIDENCE - 0.01,
                ),
            ),
            mock.patch.object(commands, "extract_command") as extraction,
            mock.patch.object(
                commands,
                "random_choice",
                return_value=ADAM_WEBSOCKET_REPEAT_PROMPTS[0],
            ),
        ):
            asyncio.run(commands.receive_command(channel, deque(maxlen=8)))

        extraction.assert_not_called()
        self.assertEqual(channel.events[-1]["status"], "repeat")
        self.assertEqual(
            channel.events[-1]["message"],
            ADAM_WEBSOCKET_REPEAT_PROMPTS[0],
        )
        self.assertEqual(
            channel.events[-1]["minimum_confidence"],
            ADAM_TEXT_CLASSIFIER_MIN_CONFIDENCE,
        )

    def test_ignores_a_very_low_confidence_command(self) -> None:
        channel = FakeWebSocket(self._message())

        with (
            mock.patch.object(
                commands,
                "infer_intent",
                return_value=IntentPrediction(
                    "check_firewall_rule",
                    ADAM_TEXT_CLASSIFIER_IGNORE_CONFIDENCE - 0.01,
                ),
            ),
            mock.patch.object(commands, "extract_command") as extraction,
        ):
            asyncio.run(commands.receive_command(channel, deque(maxlen=8)))

        extraction.assert_not_called()
        self.assertEqual(channel.events[-1]["status"], "ignored")
        self.assertEqual(
            channel.events[-1]["minimum_confidence"],
            ADAM_TEXT_CLASSIFIER_IGNORE_CONFIDENCE,
        )


if __name__ == "__main__":
    unittest.main()

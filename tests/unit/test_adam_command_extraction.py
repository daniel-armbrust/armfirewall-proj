from __future__ import annotations

import unittest

from web.adam.command_extraction.service import (
    CommandExtractionError,
    extract_command,
)


class AdamCommandExtractionTests(unittest.TestCase):
    def test_extracts_check_firewall_rule_entities(self) -> None:
        command = extract_command(
            "Check port 22/TCP from 10.0.0.5 to 192.168.1.10 via eth0.",
            "check_firewall_rule",
        )

        self.assertEqual(
            command.to_dict(),
            {
                "intent": "check_firewall_rule",
                "entities": {
                    "port": 22,
                    "protocol": "tcp",
                    "source": "10.0.0.5",
                    "destination": "192.168.1.10",
                    "interface": "eth0",
                },
            },
        )

    def test_rejects_an_intent_without_an_extractor(self) -> None:
        with self.assertRaisesRegex(
            CommandExtractionError,
            "not implemented for intent",
        ):
            extract_command(
                "Allow port 22/TCP.",
                "create_firewall_allow_rule",
            )

    def test_extracts_create_firewall_block_rule_entities(self) -> None:
        command = extract_command(
            "Block port 80/TCP from 10.0.0.5 on the firewall.",
            "create_firewall_block_rule",
        )

        self.assertEqual(
            command.to_dict(),
            {
                "intent": "create_firewall_block_rule",
                "entities": {
                    "port": 80,
                    "protocol": "tcp",
                    "source": "10.0.0.5",
                },
            },
        )

    def test_does_not_treat_firewall_as_an_interface(self) -> None:
        command = extract_command(
            "Check whether port 22/TCP is open on the firewall.",
            "check_firewall_rule",
        )
        self.assertEqual(
            command.to_dict(),
            {
                "intent": "check_firewall_rule",
                "entities": {"port": 22, "protocol": "tcp"},
            },
        )

    def test_extracts_a_spoken_port_from_the_open_rule_context(self) -> None:
        command = extract_command(
            "Check if the fourth twenty two is open.",
            "check_firewall_rule",
        )

        self.assertEqual(
            command.to_dict(),
            {
                "intent": "check_firewall_rule",
                "entities": {"port": 22},
            },
        )

    def test_extracts_a_spoken_port_when_the_asr_returns_park(self) -> None:
        command = extract_command(
            "Check if the park twenty two is open.",
            "check_firewall_rule",
        )

        self.assertEqual(
            command.to_dict(),
            {
                "intent": "check_firewall_rule",
                "entities": {"port": 22},
            },
        )

    def test_extracts_a_full_range_spoken_port(self) -> None:
        command = extract_command(
            "Check if port sixty five thousand five hundred thirty five is open.",
            "check_firewall_rule",
        )

        self.assertEqual(
            command.to_dict(),
            {
                "intent": "check_firewall_rule",
                "entities": {"port": 65535},
            },
        )

    def test_does_not_treat_a_transcribed_firewall_word_as_an_interface(self) -> None:
        command = extract_command(
            "Checked if the parts a t is or been on fire ooh all.",
            "check_firewall_rule",
        )

        self.assertEqual(
            command.to_dict(),
            {
                "intent": "check_firewall_rule",
                "entities": {},
            },
        )

if __name__ == "__main__":
    unittest.main()

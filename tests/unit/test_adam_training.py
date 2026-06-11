from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from web.adam import datasets
from web.workrequests import api as workrequests_api


TRAINING_CSV = b"""text,label
allow ssh,allow_rule
permit https,allow_rule
block telnet,block_rule
deny source address,block_rule
"""

TESTING_CSV = b"""text,label
open port 22,allow_rule
drop telnet traffic,block_rule
"""


class AdamDatasetWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database_path = self.root / "db" / "adam.db"
        self.dataset_dir = self.root / "daemons" / "adamd" / "datasets"
        self.database_path.parent.mkdir(parents=True)
        ddl_path = Path(__file__).resolve().parents[2] / "db" / "ddl" / "adam.ddl"

        with sqlite3.connect(self.database_path) as connection:
            connection.executescript(ddl_path.read_text(encoding="utf-8"))

        self.patches = [
            mock.patch.object(datasets, "ADAM_DB_PATH", self.database_path),
            mock.patch.object(datasets, "ADAM_DATASET_DIR", self.dataset_dir),
        ]

        for patcher in self.patches:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()

        self.temporary.cleanup()

    def load_dataset_pair(self) -> dict[str, object]:
        datasets.store_dataset(TRAINING_CSV, "training.csv", "training")
        return datasets.store_dataset(TESTING_CSV, "testing.csv", "testing")

    def test_training_and_testing_uploads_share_one_dataset_pair(self) -> None:
        pair = self.load_dataset_pair()

        self.assertEqual(pair["training"]["file_name"], "training.csv")
        self.assertEqual(pair["training"]["rows"], 4)
        self.assertEqual(pair["testing"]["file_name"], "testing.csv")
        self.assertEqual(pair["testing"]["rows"], 2)
        self.assertEqual(pair["status"], "uploaded")
        self.assertEqual(pair["dataset_category"], "firewall")

    def test_dataset_categories_keep_separate_active_pairs(self) -> None:
        datasets.store_dataset(
            TRAINING_CSV,
            "misc-training.csv",
            "training",
            "adam_misc",
        )
        datasets.store_dataset(TESTING_CSV, "misc-testing.csv", "testing", "adam_misc")
        datasets.store_dataset(
            TRAINING_CSV,
            "firewall-training.csv",
            "training",
            "firewall",
        )

        misc = datasets.latest_dataset("adam_misc")
        firewall = datasets.latest_dataset("firewall")

        self.assertEqual(misc["testing"]["file_name"], "misc-testing.csv")
        self.assertEqual(firewall["training"]["file_name"], "firewall-training.csv")
        self.assertIsNone(firewall["testing"])

    def test_new_training_dataset_archives_the_previous_pair(self) -> None:
        self.load_dataset_pair()
        current = datasets.store_dataset(
            TRAINING_CSV,
            "replacement.csv",
            "training",
        )

        self.assertEqual(current["training"]["file_name"], "replacement.csv")
        self.assertIsNone(current["testing"])

        with sqlite3.connect(self.database_path) as connection:
            statuses = connection.execute(
                """
                SELECT status, is_active, COUNT(*)
                FROM adam_datasets
                GROUP BY status, is_active
                ORDER BY status
                """
            ).fetchall()

        self.assertEqual(statuses, [("archived", 0, 2), ("uploaded", 1, 1)])

    def test_testing_dataset_rejects_unknown_labels(self) -> None:
        datasets.store_dataset(TRAINING_CSV, "training.csv", "training")

        with self.assertRaisesRegex(
            datasets.DatasetUploadError,
            "labels not found in training",
        ):
            datasets.store_dataset(
                b"text,label\nshow routes,unknown_label\nsecond,allow_rule\n",
                "testing.csv",
                "testing",
            )


class AdamWorkRequestTests(unittest.TestCase):
    def test_adam_training_request_uses_supplied_request_uid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            root = Path(temporary_name)
            database_path = root / "work-requests.db"
            ddl_path = Path(__file__).resolve().parents[2] / "db" / "ddl" / "work-requests.ddl"

            with sqlite3.connect(database_path) as connection:
                connection.executescript(ddl_path.read_text(encoding="utf-8"))

            request_uid = "22222222-2222-4222-8222-222222222222"

            with mock.patch.object(workrequests_api, "WORK_REQUEST_DB_PATH", database_path):
                request_id = workrequests_api.queue_work_request(
                    action="train",
                    payload={"dataset_id": "dataset"},
                    category_name="ADAM.MODEL_TRAINING",
                    request_uid=request_uid,
                )

            with sqlite3.connect(database_path) as connection:
                stored = connection.execute(
                    "SELECT request_uid, status FROM work_requests WHERE id = ?",
                    (request_id,),
                ).fetchone()

            self.assertEqual(stored, (request_uid, "queue"))

    def test_adam_delete_action_can_be_queued(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            root = Path(temporary_name)
            database_path = root / "work-requests.db"
            ddl_path = Path(__file__).resolve().parents[2] / "db" / "ddl" / "work-requests.ddl"

            with sqlite3.connect(database_path) as connection:
                connection.executescript(ddl_path.read_text(encoding="utf-8"))

            with mock.patch.object(workrequests_api, "WORK_REQUEST_DB_PATH", database_path):
                request_id = workrequests_api.queue_work_request(
                    action="delete",
                    payload={"training_uid": "11111111-1111-4111-8111-111111111111"},
                    category_name="ADAM.MODEL_TRAINING",
                )

            with sqlite3.connect(database_path) as connection:
                stored = connection.execute(
                    "SELECT action_name, status FROM work_requests WHERE id = ?",
                    (request_id,),
                ).fetchone()

            self.assertEqual(stored, ("delete", "queue"))


if __name__ == "__main__":
    unittest.main()

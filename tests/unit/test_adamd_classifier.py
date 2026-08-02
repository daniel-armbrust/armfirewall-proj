from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import joblib

from core.constants import (
    ADAM_TRAINING_CPU_QUOTA_PERCENT,
    ADAM_TRAINING_MEMORY_MAX_BYTES,
)
from daemons.adamd import adamd, text_classifier
from daemons.workreqd import workreqd
from daemons.workreqd.models import QueuedWorkRequest
from web.adam.text_classification import repository as text_classification_repository
from web.adam.text_classification import service as text_classification
from web.adam.datasets import repository, service as datasets


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


class AdamTextClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database_path = self.root / "db" / "adam.db"
        self.dataset_dir = self.root / "daemons" / "adamd" / "datasets"
        self.models_dir = self.root / "daemons" / "adamd" / "models"
        self.charts_dir = self.root / "daemons" / "adamd" / "charts"
        self.delete_staging_dir = self.root / "daemons" / "adamd" / ".delete-staging"
        self.model_path = self.models_dir / "text_classifier.joblib"
        self.database_path.parent.mkdir(parents=True)
        ddl_path = Path(__file__).resolve().parents[2] / "db" / "ddl" / "adam.ddl"

        with sqlite3.connect(self.database_path) as connection:
            connection.executescript(ddl_path.read_text(encoding="utf-8"))

        self.patches = [
            mock.patch.object(datasets, "ADAM_DB_PATH", self.database_path),
            mock.patch.object(repository, "ADAM_DB_PATH", self.database_path),
            mock.patch.object(datasets, "ADAM_DATASET_DIR", self.dataset_dir),
            mock.patch.object(text_classifier, "ADAM_DB_PATH", self.database_path),
            mock.patch.object(text_classifier, "ADAM_DATASET_DIR", self.dataset_dir),
            mock.patch.object(text_classifier, "ADAM_MODELS_DIR", self.models_dir),
            mock.patch.object(text_classifier, "ADAM_CHARTS_DIR", self.charts_dir),
            mock.patch.object(
                text_classifier,
                "ADAM_DELETE_STAGING_DIR",
                self.delete_staging_dir,
            ),
            mock.patch.object(
                text_classifier,
                "ADAM_TEXT_CLASSIFIER_MODEL_PATH",
                self.model_path,
            ),
            mock.patch.object(text_classifier, "ROOT_DIR", self.root),
            mock.patch.object(text_classification_repository, "ADAM_DB_PATH", self.database_path),
            mock.patch.object(text_classification.storage, "ADAM_CHARTS_DIR", self.charts_dir),
            mock.patch.object(text_classification.storage, "ROOT_DIR", self.root),
        ]

        for patcher in self.patches:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()

        self.temporary.cleanup()

    def test_adamd_trains_tests_and_saves_one_classifier(self) -> None:
        datasets.store_dataset(TRAINING_CSV, "training.csv", "training", "firewall")
        datasets.store_dataset(TESTING_CSV, "testing.csv", "testing", "firewall")
        request_uid = "11111111-1111-4111-8111-111111111111"
        queued = datasets.prepare_training(request_uid, "firewall")
        argv = [
            "--work-request-id",
            "1",
            "--request-uid",
            request_uid,
            "--category-name",
            "ADAM.MODEL_TRAINING",
            "--category",
            "ADAM",
            "--family",
            "",
            "--target-name",
            "model_training",
            "--action-name",
            "train",
            "--target-rule-id",
            "",
            "--payload-json",
            f'{{"training_uid":"{queued["training_uid"]}"}}',
        ]

        with mock.patch.object(adamd.logger, "info"):
            result = adamd.main(argv)

        classifier = joblib.load(self.model_path)

        with sqlite3.connect(self.database_path) as connection:
            stored = connection.execute(
                """
                SELECT status, model_joblib_filepath,
                       evaluation_chart_filepath, testing_accuracy,
                       precision_macro, recall_macro, f1_macro, is_active
                FROM adam_training_runs
                WHERE training_uid = ?
                """,
                (queued["training_uid"],),
            ).fetchone()

        self.assertEqual(result, 0)
        self.assertEqual(classifier.predict(["allow ssh"])[0], "allow_rule")
        self.assertEqual(stored[0], "success")
        self.assertEqual(
            stored[1],
            "daemons/adamd/models/text_classifier.joblib",
        )
        chart_path = self.root / stored[2]
        self.assertTrue(chart_path.is_file())
        self.assertEqual(chart_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertIsNotNone(stored[3])
        self.assertIsNotNone(stored[4])
        self.assertIsNotNone(stored[5])
        self.assertIsNotNone(stored[6])
        self.assertEqual(stored[7], 1)

        active_training = text_classification.active_training()
        self.assertEqual(active_training["model_file"], "text_classifier.joblib")
        self.assertEqual(active_training["testing_records"], 2)
        self.assertIn(queued["training_uid"], active_training["chart_url"])
        self.assertEqual(
            text_classification.evaluation_chart(queued["training_uid"]),
            chart_path,
        )

    def test_adamd_deletes_active_model_chart_and_associated_datasets(self) -> None:
        datasets.store_dataset(TRAINING_CSV, "training.csv", "training", "firewall")
        datasets.store_dataset(TESTING_CSV, "testing.csv", "testing", "firewall")
        training_request_uid = "11111111-1111-4111-8111-111111111111"
        queued = datasets.prepare_training(training_request_uid, "firewall")
        training_argv = [
            "--work-request-id",
            "1",
            "--request-uid",
            training_request_uid,
            "--category-name",
            "ADAM.MODEL_TRAINING",
            "--category",
            "ADAM",
            "--family",
            "",
            "--target-name",
            "model_training",
            "--action-name",
            "train",
            "--target-rule-id",
            "",
            "--payload-json",
            f'{{"training_uid":"{queued["training_uid"]}"}}',
        ]

        with mock.patch.object(adamd.logger, "info"):
            adamd.main(training_argv)

        chart_path = text_classification.evaluation_chart(queued["training_uid"])
        delete_argv = [
            "--work-request-id",
            "2",
            "--request-uid",
            "22222222-2222-4222-8222-222222222222",
            "--category-name",
            "ADAM.MODEL_TRAINING",
            "--category",
            "ADAM",
            "--family",
            "",
            "--target-name",
            "model_training",
            "--action-name",
            "delete",
            "--target-rule-id",
            "",
            "--payload-json",
            f'{{"training_uid":"{queued["training_uid"]}"}}',
        ]

        with mock.patch.object(adamd.logger, "info"):
            result = adamd.main(delete_argv)

        with sqlite3.connect(self.database_path) as connection:
            training_runs = connection.execute(
                "SELECT COUNT(*) FROM adam_training_runs"
            ).fetchone()[0]
            stored_datasets = connection.execute(
                "SELECT COUNT(*) FROM adam_datasets"
            ).fetchone()[0]

        self.assertEqual(result, 0)
        self.assertFalse(self.model_path.exists())
        self.assertFalse(chart_path.exists())
        self.assertEqual(list(self.dataset_dir.rglob("*.csv")), [])
        self.assertEqual(training_runs, 0)
        self.assertEqual(stored_datasets, 0)
        self.assertEqual(list(self.delete_staging_dir.iterdir()), [])
        self.assertIsNone(text_classification.active_training())


class AdamResourceLimitTests(unittest.TestCase):
    def test_workreqd_wraps_adamd_in_a_limited_systemd_service(self) -> None:
        request = QueuedWorkRequest(
            id=99,
            request_uid="11111111-1111-4111-8111-111111111111",
            category_name="ADAM.MODEL_TRAINING",
            action_name="train",
            target_rule_id=None,
            payload_json='{"training_uid":"22222222-2222-4222-8222-222222222222"}',
            category="ADAM",
            family="",
            target_name="model_training",
            script_name="adamd.py",
        )

        command = workreqd.command_for_request(request)

        self.assertEqual(command[0], "/usr/bin/systemd-run")
        self.assertIn(
            f"--property=CPUQuota={ADAM_TRAINING_CPU_QUOTA_PERCENT}%",
            command,
        )
        self.assertIn(
            f"--property=MemoryMax={ADAM_TRAINING_MEMORY_MAX_BYTES}",
            command,
        )
        self.assertIn("--setenv=OMP_NUM_THREADS=1", command)
        self.assertIn("daemons.adamd.adamd", command)


if __name__ == "__main__":
    unittest.main()

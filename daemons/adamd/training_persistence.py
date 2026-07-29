"""Persist successful ADAM training metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import sklearn

from core import db


def persist_success(
    training_run_id: int,
    metadata: dict[str, Any],
    *,
    db_path: Path,
    root_dir: Path,
    model_path: Path,
    random_state: int,
) -> None:
    """Persist training metrics and activate the new model."""
    relative_model_path = str(model_path.relative_to(root_dir))

    with db.transaction(db_path) as connection:
        db.execute_on(
            connection,
            "UPDATE adam_training_runs SET is_active = 0 WHERE is_active = 1",
        )

        cursor = db.execute_on(
            connection,
            """
            UPDATE adam_training_runs
            SET status = 'success', completed_at = CURRENT_TIMESTAMP,
                model_id = ?, model_joblib_filepath = ?,
                evaluation_chart_filepath = ?, model_sha256 = ?,
                training_records = ?, testing_records = ?, labels = ?,
                labels_count = ?, training_accuracy = ?, testing_accuracy = ?,
                precision_macro = ?, recall_macro = ?, f1_macro = ?,
                parameters_json = ?, random_state = ?,
                scikit_learn_version = ?, joblib_version = ?,
                error_message = NULL, is_active = 1
            WHERE id = ? AND status = 'running'
            """,
            (
                metadata["model_id"],
                relative_model_path,
                metadata["evaluation_chart_filepath"],
                metadata["model_sha256"],
                metadata["training_records"],
                metadata["testing_records"],
                json.dumps(metadata["labels"], ensure_ascii=False),
                len(metadata["labels"]),
                metadata["training_accuracy"],
                metadata["testing_accuracy"],
                metadata["precision_macro"],
                metadata["recall_macro"],
                metadata["f1_macro"],
                json.dumps(metadata["parameters"], sort_keys=True),
                random_state,
                sklearn.__version__,
                joblib.__version__,
                training_run_id,
            ),
        )

        if cursor.rowcount != 1:
            raise ValueError("The ADAM training result could not be persisted.")

        for category_result in metadata.get("category_results", []):
            db.execute_on(
                connection,
                """
                UPDATE adam_datasets
                SET chart_filepath = ?
                WHERE id IN (
                    SELECT d.id
                    FROM adam_training_run_datasets AS rd
                    JOIN adam_datasets AS d ON d.id = rd.dataset_id
                    WHERE rd.training_run_id = ?
                      AND d.category = ?
                      AND d.purpose = 'testing'
                )
                """,
                (
                    category_result["evaluation_chart_filepath"],
                    training_run_id,
                    category_result["category"],
                ),
            )

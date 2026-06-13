"""Remove ADAM datasets and model artifacts safely."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from core import db


def delete_classifier(
    training_uid: str,
    *,
    db_path: Path,
    dataset_dir: Path,
    models_dir: Path,
    charts_dir: Path,
    staging_dir: Path,
    normalize_uuid: Callable[[object, str], str],
    stored_artifact_path: Callable[[object, Path, str], Path],
) -> dict[str, int]:
    """Delete the active classifier and all artifacts it depends on."""
    context = _collect_delete_context(
        training_uid,
        db_path=db_path,
        dataset_dir=dataset_dir,
        models_dir=models_dir,
        charts_dir=charts_dir,
        normalize_uuid=normalize_uuid,
        stored_artifact_path=stored_artifact_path,
    )
    staging_path = _create_staging_directory(staging_dir)
    staged_files: list[tuple[Path, Path]] = []

    try:
        staged_files = _stage_artifacts(context["artifact_paths"], staging_path)
        _delete_database_records(
            context["run_ids"],
            context["dataset_ids"],
            db_path=db_path,
        )
    except Exception:
        _restore_staged_files(staged_files)
        staging_path.rmdir()
        raise

    _remove_staged_files(staged_files, staging_path)
    return {
        "training_runs": len(context["run_ids"]),
        "datasets": len(context["dataset_ids"]),
        "files": len(staged_files),
    }


def _collect_delete_context(
    training_uid: str,
    *,
    db_path: Path,
    dataset_dir: Path,
    models_dir: Path,
    charts_dir: Path,
    normalize_uuid: Callable[[object, str], str],
    stored_artifact_path: Callable[[object, Path, str], Path],
) -> dict[str, Any]:
    """Collect database records and validated artifact paths to remove."""
    normalized_uid = normalize_uuid(training_uid, "training_uid")
    training_run = db.fetch_one(
        """
        SELECT id, model_joblib_filepath, evaluation_chart_filepath
        FROM adam_training_runs
        WHERE training_uid = ? AND is_active = 1 AND status = 'success'
        """,
        (normalized_uid,),
        db_path=db_path,
    )
    if training_run is None:
        raise ValueError("The active ADAM text classifier was not found.")

    datasets = db.fetch_all(
        """
        SELECT d.id, d.dataset_uid, d.stored_filepath
        FROM adam_training_run_datasets AS rd
        JOIN adam_datasets AS d ON d.id = rd.dataset_id
        WHERE rd.training_run_id = ?
        ORDER BY d.id
        """,
        (training_run["id"],),
        db_path=db_path,
    )
    dataset_ids = [int(dataset["id"]) for dataset in datasets]
    affected_runs = _affected_runs(dataset_ids, db_path=db_path)
    run_ids = {int(run["id"]) for run in affected_runs}
    run_ids.add(int(training_run["id"]))

    artifact_paths: set[Path] = set()
    if training_run["model_joblib_filepath"]:
        artifact_paths.add(stored_artifact_path(training_run["model_joblib_filepath"], models_dir, "model"))
    if training_run["evaluation_chart_filepath"]:
        artifact_paths.add(stored_artifact_path(training_run["evaluation_chart_filepath"], charts_dir, "chart"))
    for run in affected_runs:
        if run["evaluation_chart_filepath"]:
            artifact_paths.add(stored_artifact_path(run["evaluation_chart_filepath"], charts_dir, "chart"))
    for dataset in datasets:
        normalize_uuid(dataset["dataset_uid"], "dataset_id")
        artifact_paths.add(stored_artifact_path(dataset["stored_filepath"], dataset_dir, "dataset"))

    return {"run_ids": run_ids, "dataset_ids": dataset_ids, "artifact_paths": artifact_paths}


def _affected_runs(dataset_ids: list[int], *, db_path: Path) -> list[dict[str, Any]]:
    """Find training runs that depend on the same datasets."""
    if not dataset_ids:
        return []
    placeholders = ", ".join("?" for _ in dataset_ids)
    return db.fetch_all(
        f"""
        SELECT DISTINCT r.id, r.evaluation_chart_filepath
        FROM adam_training_runs AS r
        JOIN adam_training_run_datasets AS rd ON rd.training_run_id = r.id
        WHERE rd.dataset_id IN ({placeholders})
        """,
        tuple(dataset_ids),
        db_path=db_path,
    )


def _create_staging_directory(staging_dir: Path) -> Path:
    """Create the temporary directory used for safe deletion."""
    staging_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
    return Path(tempfile.mkdtemp(prefix=".delete-", dir=staging_dir))


def _stage_artifacts(artifact_paths: set[Path], staging_path: Path) -> list[tuple[Path, Path]]:
    """Move artifacts to staging before changing database records."""
    staged_files: list[tuple[Path, Path]] = []
    for index, artifact_path in enumerate(sorted(artifact_paths)):
        if not artifact_path.exists():
            continue
        if not artifact_path.is_file():
            raise ValueError(f"The ADAM {artifact_path.name} artifact is not a regular file.")
        staged_path = staging_path / f"{index}-{artifact_path.name}"
        os.replace(artifact_path, staged_path)
        staged_files.append((artifact_path, staged_path))
    return staged_files


def _delete_database_records(run_ids: set[int], dataset_ids: list[int], *, db_path: Path) -> None:
    """Delete training relationships, runs, and datasets in one transaction."""
    placeholders = ", ".join("?" for _ in run_ids)
    with db.transaction(db_path) as connection:
        db.execute_on(connection, f"DELETE FROM adam_training_run_datasets WHERE training_run_id IN ({placeholders})", tuple(sorted(run_ids)))
        db.execute_on(connection, f"DELETE FROM adam_training_runs WHERE id IN ({placeholders})", tuple(sorted(run_ids)))
        if dataset_ids:
            dataset_placeholders = ", ".join("?" for _ in dataset_ids)
            db.execute_on(connection, f"DELETE FROM adam_datasets WHERE id IN ({dataset_placeholders})", tuple(dataset_ids))


def _restore_staged_files(staged_files: list[tuple[Path, Path]]) -> None:
    """Restore artifacts when database deletion fails."""
    for artifact_path, staged_path in reversed(staged_files):
        if staged_path.exists():
            os.replace(staged_path, artifact_path)


def _remove_staged_files(staged_files: list[tuple[Path, Path]], staging_path: Path) -> None:
    """Permanently remove successfully staged artifacts."""
    for _, staged_path in staged_files:
        staged_path.unlink(missing_ok=True)
    staging_path.rmdir()

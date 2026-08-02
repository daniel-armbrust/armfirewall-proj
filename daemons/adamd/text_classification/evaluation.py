"""Evaluate the ADAM classifier and publish its chart."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

# ADAMD runs without a display server; select a non-interactive backend before
# importing pyplot.
os.environ.setdefault("MPLBACKEND", "Agg")

from matplotlib import pyplot as plt
from sklearn.metrics import confusion_matrix


def publish_evaluation_chart(
    training_uid: str,
    metadata: dict[str, Any],
    expected_labels: list[str],
    predicted_labels: Any,
    *,
    charts_dir: Path,
    filename_prefix: str,
    chart_dpi: int,
) -> Path:
    """Generate and atomically publish one training evaluation chart."""
    labels = [str(value) for value in metadata["labels"]]
    matrix = confusion_matrix(expected_labels, predicted_labels, labels=labels)

    metric_names = [
        "Training accuracy",
        "Testing accuracy",
        "Precision macro",
        "Recall macro",
        "F1 macro",
    ]

    metric_values = [
        metadata["training_accuracy"],
        metadata["testing_accuracy"],
        metadata["precision_macro"],
        metadata["recall_macro"],
        metadata["f1_macro"],
    ]

    chart_path = charts_dir / f"{filename_prefix}_{training_uid}.png"
    charts_dir.mkdir(parents=True, exist_ok=True, mode=0o750)

    descriptor, temporary_name = tempfile.mkstemp(
        dir=charts_dir,
        prefix=".text_classifier-",
        suffix=".png.tmp",
    )

    os.close(descriptor)

    temporary_path = Path(temporary_name)
    figure = None

    try:
        figure_width = min(18.0, max(11.0, 8.0 + len(labels) * 0.45))
        figure_height = min(12.0, max(5.2, 4.0 + len(labels) * 0.35))

        figure, axes = plt.subplots(
            1,
            2,
            figsize=(figure_width, figure_height),
            gridspec_kw={"width_ratios": (1.0, 1.35)},
        )

        metric_axis, matrix_axis = axes

        bars = metric_axis.barh(
            metric_names,
            metric_values,
            color=["#30d878", "#15c5a5", "#40a9ff", "#ffb84d", "#d978ff"],
        )

        metric_axis.set_xlim(0.0, 1.0)
        metric_axis.set_xlabel("Score")
        metric_axis.set_title("Classifier metrics")
        metric_axis.grid(axis="x", alpha=0.2)
        metric_axis.invert_yaxis()

        for bar, value in zip(bars, metric_values, strict=True):
            metric_axis.text(
                min(float(value) + 0.02, 0.98),
                bar.get_y() + bar.get_height() / 2,
                f"{float(value):.1%}",
                va="center",
                ha="left" if float(value) <= 0.9 else "right",
                fontsize=9,
            )

        image = matrix_axis.imshow(matrix, interpolation="nearest", cmap="Greens")
        matrix_axis.set_title("Testing confusion matrix")
        matrix_axis.set_xlabel("Predicted label")
        matrix_axis.set_ylabel("Expected label")
        matrix_axis.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
        matrix_axis.set_yticks(range(len(labels)), labels)
        annotation_size = max(5, 10 - len(labels) // 4)
        threshold = float(matrix.max()) / 2 if matrix.size else 0.0

        for row_index in range(matrix.shape[0]):
            for column_index in range(matrix.shape[1]):
                value = int(matrix[row_index, column_index])

                matrix_axis.text(
                    column_index,
                    row_index,
                    str(value),
                    ha="center",
                    va="center",
                    color="white" if value > threshold else "black",
                    fontsize=annotation_size,
                )

        figure.colorbar(image, ax=matrix_axis, fraction=0.046, pad=0.04)
        figure.suptitle("Adam - Text Classifier Evaluation", fontweight="bold")
        figure.tight_layout()

        figure.savefig(
            temporary_path,
            format="png",
            dpi=chart_dpi,
            bbox_inches="tight",
        )

        os.chmod(temporary_path, 0o640)

        with temporary_path.open("rb") as chart_file:
            os.fsync(chart_file.fileno())

        os.replace(temporary_path, chart_path)

        return chart_path
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        if figure is not None:
            plt.close(figure)

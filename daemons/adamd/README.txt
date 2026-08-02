ArmFirewall ADAM Training Daemon
================================

adamd is a one-shot worker for ADAM text-classification lifecycle requests. It
is dispatched by workreqd for one queued request and exits when that request
finishes. It is not a persistent daemon and must not be registered in
Supervisor.

Responsibilities
----------------

The web application owns CSV upload validation and dataset persistence. For one
selected dataset category, it stores one training CSV and one testing CSV, then
creates an adam_training_runs record and queues its training_uid.

workreqd owns request dispatch. It starts this worker with:

    python -m daemons.adamd.adamd

adamd validates the work-request arguments and delegates the text-classification
operation to text_classification/service.py.

Training Flow
-------------

1. The web application stores the selected training and testing CSV files under
   ROOT_DIR/daemons/adamd/datasets/.
2. The web application creates one queued training run associated with exactly
   that dataset pair.
3. workreqd dispatches the request with the training_uid payload.
4. adamd marks the run as running.
5. text_classification/service.py loads and validates the two CSV files.
6. A deterministic TfidfVectorizer and LogisticRegression pipeline is trained
   and evaluated against the testing CSV.
7. The model and one evaluation chart are atomically published.
8. The training metadata and metrics are persisted and the run becomes active.

The training run is marked as failed if any training step raises an exception.

Deletion Flow
-------------

A delete work request targets the active training_uid. The worker safely stages
model, chart, and dataset artifacts, removes the related database records in a
transaction, and removes the staged files only after the transaction succeeds.

Payload
-------

Both training and deletion requests require a valid UUID:

    {"training_uid": "5b6789b4-36a2-4e33-96fe-cc98cc9cf236"}

For manual diagnostics:

    python -m daemons.adamd.adamd \
        --work-request-id 1 \
        --request-uid 11111111-1111-4111-8111-111111111111 \
        --category-name ADAM.MODEL_TRAINING \
        --category ADAM \
        --family MACHINE_LEARNING \
        --target-name model_training \
        --action-name train \
        --target-rule-id "" \
        --payload-json '{"training_uid":"5b6789b4-36a2-4e33-96fe-cc98cc9cf236"}'

Use --action-name delete to remove the active classifier identified by the
payload.

Package Structure
-----------------

adamd.py
    Work-request parser and lifecycle dispatcher.

text_classification/service.py
    Training orchestration, validation, publication, persistence, and deletion
    entry points.

text_classification/training.py
    scikit-learn pipeline construction and atomic model publication.

text_classification/evaluation.py
    Evaluation chart generation and atomic chart publication.

text_classification/datasets.py
    Training-run lookup and safe CSV/artifact path handling.

text_classification/persistence.py
    Successful training metadata and metric persistence.

text_classification/state.py
    Queued, running, and failed training-run transitions.

text_classification/cleanup.py
    Safe staging and deletion of training artifacts and database records.

Artifacts
---------

The configured ADAM model directory contains the active joblib classifier. The
configured chart directory contains its evaluation chart. Dataset CSV files,
model artifacts, and charts are constrained to their configured directories
before they are read, published, or deleted.

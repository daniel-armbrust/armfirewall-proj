ArmFirewall ADAM Training Daemon
================================

adamd is a one-shot executor for asynchronous ADAM model training. It is started
by workreqd for one queued work request and exits when that request finishes. It
is not a persistent daemon and must not be registered in Supervisor.

Execution Flow
--------------

1. The web application stores each immutable CSV under
   ROOT_DIR/daemons/adamd/datasets/<UUID>.csv.
2. The web application creates one training run associated with every complete
   active dataset category and queues its training_uid.
3. workreqd dispatches the request to adamd.
4. adamd validates the request and loads every associated CSV.
5. A TfidfVectorizer and LogisticRegression pipeline trains the classifier.
6. adamd atomically saves the joblib pipeline under
   ROOT_DIR/daemons/adamd/models/ and exits.

Required payload:

    {"training_uid": "5b6789b4-36a2-4e33-96fe-cc98cc9cf236"}

For manual diagnostics, use:

    python -m daemons.adamd.adamd \
        --work-request-id 1 \
        --request-uid example-request \
        --category-name ADAM.MODEL_TRAINING \
        --category ADAM \
        --family MACHINE_LEARNING \
        --target-name model_training \
        --action-name train \
        --target-rule-id "" \
        --payload-json '{"training_uid":"5b6789b4-36a2-4e33-96fe-cc98cc9cf236"}'

Artifacts
---------

daemons/adamd/models/adam-intent-<UUID>.joblib
    Fitted scikit-learn Pipeline ready for prediction.

daemons/adamd/models/adam-intent-<UUID>.json
    Training provenance, classes, record count and training accuracy.

daemons/adamd/models/active.json
    Atomic pointer containing metadata for the active inference model.

Responsibility Boundary
-----------------------

The web process validates uploads and queues work. workreqd owns dispatch and
status tracking. adamd owns one training execution and then terminates.

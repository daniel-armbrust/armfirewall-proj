PRAGMA foreign_keys = ON;

-- Stores each ADAM intent classifier training execution and its artifacts.
-- File paths are always relative to ROOT_DIR.
-- work_request_uid is an external reference to work_requests.request_uid in
-- work-requests.db because SQLite cannot enforce foreign keys across databases.
CREATE TABLE IF NOT EXISTS adam_training_runs (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     training_uid TEXT NOT NULL UNIQUE,
     work_request_uid TEXT NOT NULL UNIQUE,

     dataset_id TEXT NOT NULL,
     dataset_csv_filepath TEXT NOT NULL,
     dataset_csv_filename TEXT NOT NULL,
     dataset_sha256 TEXT NOT NULL CHECK (length(dataset_sha256) = 64),

     status TEXT NOT NULL DEFAULT 'queue' CHECK (
          status IN (
               'queue',
               'running',
               'success',
               'failed'
          )
     ),

     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     started_at TEXT,
     completed_at TEXT,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

     model_id TEXT UNIQUE,
     model_joblib_filepath TEXT,
     model_sha256 TEXT CHECK (
          model_sha256 IS NULL OR length(model_sha256) = 64
     ),

     training_records INTEGER NOT NULL DEFAULT 0 CHECK (training_records >= 0),
     testing_records INTEGER NOT NULL DEFAULT 0 CHECK (testing_records >= 0),
     labels TEXT NOT NULL DEFAULT '[]',
     labels_count INTEGER NOT NULL DEFAULT 0 CHECK (labels_count >= 0),

     training_accuracy REAL CHECK (
          training_accuracy IS NULL
          OR training_accuracy BETWEEN 0.0 AND 1.0
     ),
     testing_accuracy REAL CHECK (
          testing_accuracy IS NULL
          OR testing_accuracy BETWEEN 0.0 AND 1.0
     ),
     precision_macro REAL CHECK (
          precision_macro IS NULL
          OR precision_macro BETWEEN 0.0 AND 1.0
     ),
     recall_macro REAL CHECK (
          recall_macro IS NULL
          OR recall_macro BETWEEN 0.0 AND 1.0
     ),
     f1_macro REAL CHECK (
          f1_macro IS NULL
          OR f1_macro BETWEEN 0.0 AND 1.0
     ),

     algorithm TEXT NOT NULL DEFAULT 'LogisticRegression',
     vectorizer TEXT NOT NULL DEFAULT 'TfidfVectorizer',
     parameters_json TEXT NOT NULL DEFAULT '{}',
     random_state INTEGER,
     scikit_learn_version TEXT,
     joblib_version TEXT,

     error_message TEXT,
     is_active INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),

     CHECK (started_at IS NULL OR started_at >= created_at),
     CHECK (completed_at IS NULL OR started_at IS NOT NULL),
     CHECK (completed_at IS NULL OR completed_at >= started_at),
     CHECK (
          status != 'success'
          OR (
               completed_at IS NOT NULL
               AND model_id IS NOT NULL
               AND model_joblib_filepath IS NOT NULL
               AND model_sha256 IS NOT NULL
               AND labels_count >= 2
          )
     ),
     CHECK (status != 'failed' OR completed_at IS NOT NULL),
     CHECK (is_active = 0 OR status = 'success')
);

-- Speeds up the training history view and pending/running lookups.
CREATE INDEX IF NOT EXISTS idx_adam_training_runs_status_created_at
ON adam_training_runs (status, created_at);

-- Speeds up lookup of every training execution for one dataset.
CREATE INDEX IF NOT EXISTS idx_adam_training_runs_dataset_id
ON adam_training_runs (dataset_id, created_at);

-- Speeds up correlation with the asynchronous work request dispatcher.
CREATE INDEX IF NOT EXISTS idx_adam_training_runs_work_request_uid
ON adam_training_runs (work_request_uid);

-- Guarantees that only one successfully trained model is active for inference.
CREATE UNIQUE INDEX IF NOT EXISTS uq_adam_training_runs_active
ON adam_training_runs (is_active)
WHERE is_active = 1;

-- Maintains the row modification timestamp.
CREATE TRIGGER IF NOT EXISTS adam_training_runs_touch_updated_at
AFTER UPDATE ON adam_training_runs
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
     UPDATE adam_training_runs
        SET updated_at = CURRENT_TIMESTAMP
      WHERE id = OLD.id;
END;

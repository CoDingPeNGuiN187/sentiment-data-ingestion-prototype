-- SQLite schema for Google Play review ingestion prototype

CREATE TABLE IF NOT EXISTS apps (
    app_id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    platform_app_id TEXT NOT NULL,
    app_name TEXT NOT NULL,
    country TEXT,
    language TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (platform, platform_app_id, country, language)
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    ingestion_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id INTEGER NOT NULL,
    requested_count INTEGER,
    collected_count INTEGER,
    inserted_count INTEGER,
    duplicate_count INTEGER,
    runtime_seconds REAL,
    sort_method TEXT,
    status TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    notes TEXT,

    FOREIGN KEY (app_id) REFERENCES apps(app_id)
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id INTEGER NOT NULL,
    ingestion_run_id INTEGER,

    platform_review_id TEXT NOT NULL,
    review_text TEXT NOT NULL,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    review_date TIMESTAMP,
    app_version TEXT,
    thumbs_up_count INTEGER,
    developer_response TEXT,

    collected_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (app_id) REFERENCES apps(app_id),
    FOREIGN KEY (ingestion_run_id) REFERENCES ingestion_runs(ingestion_run_id),
    UNIQUE (app_id, platform_review_id)
);

CREATE TABLE IF NOT EXISTS review_quality_features (
    review_quality_id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER NOT NULL,

    review_char_length INTEGER,
    review_word_count INTEGER,
    is_very_short BOOLEAN,
    is_generic_text BOOLEAN,
    is_low_signal BOOLEAN,
    is_duplicate_text BOOLEAN,
    detected_language TEXT,

    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (review_id) REFERENCES reviews(review_id)
);
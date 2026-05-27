-- Table 1: apps
CREATE TABLE apps (
    app_id SERIAL PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,
    platform_app_id VARCHAR(255) NOT NULL,
    app_name VARCHAR(255) NOT NULL,
    country VARCHAR(10),
    language VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (platform, platform_app_id, country, language)
);

-- Table 2: ingestion_runs
CREATE TABLE ingestion_runs(
    ingestion_run_id SERIAL PRIMARY KEY,
    app_id INTEGER NOT NULL REFERENCES apps(app_id),
    requested_count INTEGER,
    colletced_count INTEGER,
    runtime_seconds NUMERIC(10,2)
    sort_method VARCHAR(100)
    status VARCHAR(50)
    started_at TIMESTAMP
    completed_at TIMESTAMP
    notes TEXT
);

-- Table 3: reviews 
CREATE TABLE reviews(
    review_id SERIAL PRIMARY KEY,
    app_id INTEGER NOT NULL REFERENCES apps(app_id),
    ingestion_run_id INTEGER REFERENCES ingestion_runs(ingestion_run_id),

    platform_review_id VARCHAR(255) NOT NULL,
    review_text TEXT NOT NULL.
    rating INTEGER CHECK (rating BETWEEN 1 AND 5)
    review_date TIMESTAMP,
    app_version VARCHAR(100),
    thumbs_up_count INTEGER,
    developer_response TEXT,
    
    collected_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(app_id, platform_review_id)
);

-- Table 4: review_quality_features
CREATE TABLE review_quality_features (
    review_quality_id SERIAL PRIMARY KEY,
    review_id INTEGER NOT NULL REFERENCES reviews(review_id),

    review_char_length INTEGER,
    review_word_count INTEGER,
    is_very_short BOOLEAN,
    is_generic_text BOOLEAN,
    is_low_signal BOOLEAN,
    is_duplicate_text BOOLEAN,
    detected_language VARCHAR(20),

    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
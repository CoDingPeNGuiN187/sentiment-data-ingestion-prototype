# Ingestion Frequency Test

## Goal

Test how the Google Play to SQLite ingestion prototype behaves when the collection process is run repeatedly at short intervals.

## Test Setup

- Source: Google Play Store
- App: ChatGPT (`com.openai.chatgpt`)
- Database: SQLite
- Batch size: configured in `scripts/ingest_google_play_to_sqlite.py`
- Deduplication key: `(app_id, platform_review_id)`

## Metrics Tracked

- Requested reviews
- Collected reviews
- Inserted reviews
- Duplicate reviews skipped
- Duplicate rate
- New review rate
- Runtime
- Database total review count after each run
- Run status / errors

## Results

| Run | Wait Before Run | Collected | Inserted | Duplicates | Duplicate Rate | New Review Rate | Runtime | Total Reviews After Run | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| long_classification_baseline | 0s | 1000 | 35 | 965 | 0.965 | 0.035 | 1.28s | 1056 | success |
| long_classification_30_min | 1800s | 1000 | 31 | 969 | 0.969 | 0.031 | 1.78s | 1087 | success |
| long_classification_1_hour | 3600s | 1000 | 108 | 892 | 0.892 | 0.108 | 1.99s | 1195 | success |

## Initial Observations

TBD. After running the test, summarize whether repeated ingestion mostly produced new reviews or duplicates, whether runtime changed, and whether any source-side or database-side issues appeared.

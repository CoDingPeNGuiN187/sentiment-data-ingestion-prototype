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
| baseline | 0s | 1000 | 1000 | 0 | 0.0 | 1.0 | 1.58s | 2000 | success |
| 1_min_repeat_1 | 60s | 1000 | 9 | 991 | 0.991 | 0.009 | 0.81s | 2009 | success |
| 1_min_repeat_2 | 60s | 1000 | 2 | 998 | 0.998 | 0.002 | 1.03s | 2011 | success |
| 5_min_repeat | 300s | 1000 | 22 | 978 | 0.978 | 0.022 | 2.84s | 2033 | success |

## Initial Observations

TBD. After running the test, summarize whether repeated ingestion mostly produced new reviews or duplicates, whether runtime changed, and whether any source-side or database-side issues appeared.

## Recurring Ingestion behavior
## Frequency Test Results

| Run | Wait Before Run | Collected | Inserted | Duplicates | Duplicate Rate | New Review Rate | Runtime | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 0s | 1,000 | 115 | 885 | 88.5% | 11.5% | 1.26s | success |
| 1_min_repeat_1 | 60s | 1,000 | 7 | 993 | 99.3% | 0.7% | 0.94s | success |
| 1_min_repeat_2 | 60s | 1,000 | 3 | 997 | 99.7% | 0.3% | 2.64s | success |
| 5_min_repeat | 300s | 1,000 | 30 | 970 | 97.0% | 3.0% | 0.99s | success |
| baseline_long_interval_test | 0s | 1,000 | 0 | 1,000 | 100.0% | 0.0% | 0.74s | success |
| 15_min_repeat | 900s | 1,000 | 72 | 928 | 92.8% | 7.2% | 1.52s | success |
| 30_min_repeat | 1,800s | 1,000 | 157 | 843 | 84.3% | 15.7% | 0.93s | success |
| 1_hour_repeat | 3,600s | 1,000 | 1,000 | 0 | 0.0% | 100.0% | 0.95s | success |

## Initial Observations

The repeated ingestion test completed successfully across all tested intervals. Each run collected 1,000 reviews and completed with `success` status, suggesting that the current Google Play ingestion prototype is stable for repeated short-interval runs at this batch size.

Shorter intervals produced mostly duplicate reviews. At the 1-minute frequency, only 7 and 3 new reviews were inserted in the two repeated runs, while duplicate rates were above 99%. The 5-minute run inserted 30 new reviews, with a 97% duplicate rate. This suggests that very high-frequency ingestion may not be efficient for this source and app, because most fetched reviews have already been collected.

As the interval increased, the number of newly inserted reviews also increased. The 15-minute run inserted 72 new reviews, and the 30-minute run inserted 157 new reviews. In this test, the 1-hour repeat inserted 1,000 new reviews with no duplicates, suggesting that longer intervals may provide a much higher yield of new review data.

Runtime remained low and relatively stable across all runs, generally around 1 second, with one 1-minute repeat taking 2.64 seconds. No source-side failures or database insertion errors were observed during this test.

#
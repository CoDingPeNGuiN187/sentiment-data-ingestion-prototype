# Ingestion Monitoring Report

## Purpose

This report summarizes operational signals for the review ingestion pipeline.

The goal is to understand whether the pipeline would be healthy if it were running unattended in a production-like setting.

The report tracks both pipeline health and source behavior.

## Overall Pipeline Health

- Total ingestion runs: 9
- Successful runs: 9
- Failed runs: 0
- Success rate: 100.00%
- Failure rate: 0.00%
- Average runtime: 1.40 seconds
- Average throughput: 779.98 records/second

## Data Collection Metrics

- Total records collected: 9000
- Total records inserted: 1195
- Total duplicate records: 7805
- Average records collected per run: 1000.00
- Average records inserted per run: 132.78
- Average duplicate rate: 86.72%

## Source-Window and Freshness Metrics

- Average source-window overlap rate: 97.56%
- Total ingestion-category newly-created records: 195
- Total ingestion-category old-but-new-to-database records: 0
- Total records newly created since previous run time: 0.00
- Total inserted records that were new since previous run time: 0.00
- Total inserted records that were old relative to previous run time: 195.00


## Latest Run Snapshot

- Latest ingestion run ID: 9
- Status: success
- Collected records: 1000
- Inserted records: 108
- Duplicate rate: 89.20%
- Source-window overlap rate: 89.20%
- Ingestion-category newly-created count: 108
- Ingestion-category old-but-new-to-database count: 0
- Newly created since previous run time: 0.00
- Inserted and new since previous run time: 0.00
- Inserted but old relative to previous run time: 108.00
- Runtime: 1.99 seconds
- Throughput: 502.51 records/second


## Important Metric Definitions

### Database novelty

A record is new to the database if its platform review ID has not been inserted into the `reviews` table before.

This is measured through `inserted_count`.

### Source freshness

A record is genuinely fresh relative to the previous run if its `review_date` is later than the previous ingestion run's `completed_at` timestamp.

This is measured through `newly_created_since_previous_run_time_count`.

### Why this distinction matters

A record can be new to the database but not genuinely new on the source.

This can happen when the source exposes a rolling latest-review window. A review may not appear in one returned window, but may appear in a later window even though it was created before the previous ingestion run.

Therefore, `inserted_count` should not be interpreted as a standalone freshness metric.

## Interpretation

The monitoring layer separates pipeline health from source behavior.

Pipeline health is measured using success rate, failure rate, collected records, inserted records, runtime, and throughput.

Source behavior is measured using duplicate rate, source-window overlap rate, time-based freshness, and old-but-new-to-database behavior.

A key distinction is that records newly inserted into the database are not necessarily genuinely new on the source. Inserted count should be evaluated together with source-window overlap and time-based freshness classification.

## Potential Warning Signals

The following signals may indicate pipeline or source-side issues:

1. Collected records drop significantly below the expected batch size.
2. Failure rate increases.
3. Runtime spikes relative to previous runs.
4. Throughput drops sharply.
5. Duplicate rate changes unexpectedly.
6. Source-window overlap remains very high when new data is expected.
7. Newly-created-since-previous-run count remains zero when freshness is required.
8. Inserted records are mostly old relative to the previous run time, suggesting that database novelty is not the same as true source freshness.

## Output Files

- Run-level monitoring CSV: `outputs/monitoring/ingestion_monitoring_summary.csv`
- Markdown monitoring report: `docs/ingestion_monitoring_report.md`

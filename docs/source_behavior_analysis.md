# Source Behavior Analysis

## Purpose

This report analyzes the observable behavior of the Google Play review source.

The goal is to understand whether the source behaves like a true incremental feed, a rolling latest-review window, or something less stable.

## Source Window Date Span

This metric measures the time range covered by the returned review window.

For each ingestion run, it calculates:

- newest review timestamp in the returned window
- oldest review timestamp in the returned window
- total time span covered by the returned window

### Summary

- Average source-window time span: 366.86 minutes
- Latest run source-window time span: 446.43 minutes
- Latest run oldest review date: 2026-06-08 13:36:44+00:00
- Latest run newest review date: 2026-06-08 21:03:10+00:00

## Date Ordering

This checks whether the returned reviews are strictly ordered from newest to oldest by review timestamp.

### Summary

- Average date-order violation rate: 0.00%

A low violation rate suggests that the source is mostly ordered by review timestamp.
A high violation rate suggests that the source may be affected by ranking, indexing, moderation, or other source-side logic.


## Latest Consecutive-Run Position Stability

- Previous run ID: 8.0
- Current run ID: 9.0
- Overlap count: 892.0
- Overlap rate: 89.20%
- Average position shift: 108.00
- Median position shift: 108.00
- Max position shift: 108.00


## First-Seen Delay

This estimates the delay between a review's source timestamp and the first time it appears in our collected source windows.

### Summary

- Average first-seen delay: 1861.20 minutes
- Median first-seen delay: 1885.68 minutes

This metric helps estimate the level of freshness that is realistically achievable.

If first-seen delay is high, then collecting more frequently may not produce fresher records, because the source itself may not expose reviews immediately.

## Interpretation

These metrics help answer the question: what is the actual behavior of the source?

The main signals are:

1. Source-window date span tells us how much review history the latest returned window covers.
2. Source-window overlap tells us whether consecutive runs return mostly the same records.
3. Position shift tells us whether overlapping records maintain a stable order.
4. Date-order violation rate tells us whether Sort.NEWEST behaves like strict timestamp sorting.
5. First-seen delay helps estimate how quickly newly created reviews become visible to the pipeline.

Together, these metrics help distinguish source-side limitations from pipeline-side performance.

## Output Files

- Run-level source behavior summary: `outputs/source_behavior/source_behavior_run_level_summary.csv`
- Position stability summary: `outputs/source_behavior/source_behavior_position_stability.csv`
- First-seen delay summary: `outputs/source_behavior/source_behavior_first_seen_delay.csv`

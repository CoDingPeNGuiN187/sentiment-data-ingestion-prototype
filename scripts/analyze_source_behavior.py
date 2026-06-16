import sqlite3
from pathlib import Path

import pandas as pd


DATABASE_PATH = Path("data/database/reviews.db")

OUTPUT_DIR = Path("outputs/source_behavior")
CSV_OUTPUT_PATH = OUTPUT_DIR / "source_behavior_summary.csv"

DOCS_DIR = Path("docs")
MARKDOWN_OUTPUT_PATH = DOCS_DIR / "source_behavior_analysis.md"


def connect_database():
    """
    Connect to the local SQLite database.
    """
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DATABASE_PATH}. "
            "Run the ingestion pipeline first."
        )

    return sqlite3.connect(DATABASE_PATH)


def load_source_window_reviews(conn):
    """
    Load all records returned by the source across ingestion runs.

    This table should contain one row per review returned by the source,
    including duplicates.
    """
    query = """
    SELECT
        ingestion_run_id,
        app_id,
        platform_review_id,
        review_date,
        returned_position,
        collected_at,
        ingestion_category,
        is_existing_review,
        is_newly_created,
        is_old_but_new_to_database
    FROM source_window_reviews
    ORDER BY ingestion_run_id, returned_position;
    """

    return pd.read_sql_query(query, conn)


def parse_datetime_columns(df):
    """
    Convert review_date and collected_at into timezone-aware datetime values.
    """
    df = df.copy()
    df["review_date_parsed"] = pd.to_datetime(
        df["review_date"],
        errors="coerce",
        utc=True
    )
    df["collected_at_parsed"] = pd.to_datetime(
        df["collected_at"],
        errors="coerce",
        utc=True
    )
    return df


def compute_window_date_span(source_df):
    """
    For each ingestion run, calculate the date range covered by the returned source window.

    This answers:
    - What is the newest review_date in the returned 1000 reviews?
    - What is the oldest review_date in the returned 1000 reviews?
    - How many minutes does the returned window cover?
    """
    rows = []

    for run_id, group in source_df.groupby("ingestion_run_id"):
        valid_dates = group["review_date_parsed"].dropna()

        if valid_dates.empty:
            min_review_date = None
            max_review_date = None
            window_span_minutes = None
        else:
            min_review_date = valid_dates.min()
            max_review_date = valid_dates.max()
            window_span_minutes = (
                max_review_date - min_review_date
            ).total_seconds() / 60

        rows.append(
            {
                "ingestion_run_id": run_id,
                "source_window_size": group["platform_review_id"].nunique(),
                "min_review_date": min_review_date,
                "max_review_date": max_review_date,
                "source_window_time_span_minutes": window_span_minutes,
            }
        )

    return pd.DataFrame(rows)


def compute_position_stability(source_df):
    """
    Compare consecutive ingestion runs and calculate how much overlapping reviews moved
    in returned_position.

    This answers:
    - Does the source return overlapping reviews in roughly the same order?
    - Or does the source reshuffle/rerank records across runs?

    Example:
    Review A is position 10 in run 1 and position 13 in run 2.
    position_shift = abs(13 - 10) = 3
    """
    rows = []

    run_ids = sorted(source_df["ingestion_run_id"].unique())

    for i in range(1, len(run_ids)):
        previous_run_id = run_ids[i - 1]
        current_run_id = run_ids[i]

        previous_run = source_df[
            source_df["ingestion_run_id"] == previous_run_id
        ][["platform_review_id", "returned_position"]].copy()

        current_run = source_df[
            source_df["ingestion_run_id"] == current_run_id
        ][["platform_review_id", "returned_position"]].copy()

        previous_run = previous_run.rename(
            columns={"returned_position": "previous_position"}
        )
        current_run = current_run.rename(
            columns={"returned_position": "current_position"}
        )

        merged = current_run.merge(
            previous_run,
            on="platform_review_id",
            how="inner"
        )

        if merged.empty:
            overlap_count = 0
            avg_position_shift = None
            median_position_shift = None
            max_position_shift = None
        else:
            merged["position_shift"] = (
                merged["current_position"] - merged["previous_position"]
            ).abs()

            overlap_count = len(merged)
            avg_position_shift = merged["position_shift"].mean()
            median_position_shift = merged["position_shift"].median()
            max_position_shift = merged["position_shift"].max()

        current_window_size = current_run["platform_review_id"].nunique()
        overlap_rate = (
            overlap_count / current_window_size
            if current_window_size > 0
            else None
        )

        rows.append(
            {
                "previous_run_id": previous_run_id,
                "current_run_id": current_run_id,
                "overlap_count": overlap_count,
                "overlap_rate": overlap_rate,
                "avg_position_shift": avg_position_shift,
                "median_position_shift": median_position_shift,
                "max_position_shift": max_position_shift,
            }
        )

    return pd.DataFrame(rows)


def compute_date_order_violations(source_df):
    """
    Check whether the returned window is sorted by review_date from newest to oldest.

    If returned_position increases, review_date should usually get older.

    A date order violation happens when a later returned position has a newer review_date
    than the previous returned position.

    This answers:
    - Is Sort.NEWEST behaving like a strict timestamp ordering?
    - Or is the source ordering affected by other factors?
    """
    rows = []

    for run_id, group in source_df.groupby("ingestion_run_id"):
        group = group.sort_values("returned_position").copy()
        dates = group["review_date_parsed"].tolist()

        violation_count = 0
        comparable_pairs = 0

        for i in range(1, len(dates)):
            previous_date = dates[i - 1]
            current_date = dates[i]

            if pd.isna(previous_date) or pd.isna(current_date):
                continue

            comparable_pairs += 1

            # If the current item appears later in the returned list but has a newer date,
            # the list is not strictly newest-to-oldest.
            if current_date > previous_date:
                violation_count += 1

        violation_rate = (
            violation_count / comparable_pairs
            if comparable_pairs > 0
            else None
        )

        rows.append(
            {
                "ingestion_run_id": run_id,
                "date_order_violation_count": violation_count,
                "date_order_comparable_pairs": comparable_pairs,
                "date_order_violation_rate": violation_rate,
            }
        )

    return pd.DataFrame(rows)


def compute_first_seen_delay(source_df):
    """
    For each unique review, calculate the time between its review_date and the first time
    it appeared in our source windows.

    This answers:
    - Does the source expose reviews immediately?
    - Or is there an observable delay between review creation and first exposure?

    first_seen_delay_minutes = first_seen_collected_at - review_date
    """
    rows = []

    valid = source_df.dropna(
        subset=["platform_review_id", "review_date_parsed", "collected_at_parsed"]
    ).copy()

    for review_id, group in valid.groupby("platform_review_id"):
        first_seen_row = group.sort_values("collected_at_parsed").iloc[0]

        review_date = first_seen_row["review_date_parsed"]
        first_seen_at = first_seen_row["collected_at_parsed"]

        delay_minutes = (first_seen_at - review_date).total_seconds() / 60

        rows.append(
            {
                "platform_review_id": review_id,
                "review_date": review_date,
                "first_seen_at": first_seen_at,
                "first_seen_delay_minutes": delay_minutes,
            }
        )

    return pd.DataFrame(rows)


def combine_run_level_metrics(
    window_span_df,
    date_order_df,
):
    """
    Combine run-level source behavior metrics into one table.
    """
    summary_df = window_span_df.merge(
        date_order_df,
        on="ingestion_run_id",
        how="left"
    )

    return summary_df


def write_csv_outputs(
    run_level_summary_df,
    position_stability_df,
    first_seen_delay_df,
):
    """
    Write CSV outputs for source behavior analysis.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    run_level_summary_df.to_csv(
        OUTPUT_DIR / "source_behavior_run_level_summary.csv",
        index=False
    )

    position_stability_df.to_csv(
        OUTPUT_DIR / "source_behavior_position_stability.csv",
        index=False
    )

    first_seen_delay_df.to_csv(
        OUTPUT_DIR / "source_behavior_first_seen_delay.csv",
        index=False
    )


def format_number(value):
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.2f}"


def format_percent(value):
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.2%}"


def write_markdown_report(
    run_level_summary_df,
    position_stability_df,
    first_seen_delay_df,
):
    """
    Write a human-readable source behavior analysis report.
    """
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    avg_window_span = run_level_summary_df[
        "source_window_time_span_minutes"
    ].dropna().mean()

    avg_date_order_violation_rate = run_level_summary_df[
        "date_order_violation_rate"
    ].dropna().mean()

    avg_overlap_rate = position_stability_df[
        "overlap_rate"
    ].dropna().mean()

    avg_position_shift = position_stability_df[
        "avg_position_shift"
    ].dropna().mean()

    median_position_shift = position_stability_df[
        "median_position_shift"
    ].dropna().median()

    median_first_seen_delay = first_seen_delay_df[
        "first_seen_delay_minutes"
    ].dropna().median()

    avg_first_seen_delay = first_seen_delay_df[
        "first_seen_delay_minutes"
    ].dropna().mean()

    latest_window = run_level_summary_df.iloc[-1]
    latest_position = position_stability_df.iloc[-1] if not position_stability_df.empty else None

    if latest_position is not None:
        latest_position_section = f"""
## Latest Consecutive-Run Position Stability

- Previous run ID: {latest_position["previous_run_id"]}
- Current run ID: {latest_position["current_run_id"]}
- Overlap count: {latest_position["overlap_count"]}
- Overlap rate: {format_percent(latest_position["overlap_rate"])}
- Average position shift: {format_number(latest_position["avg_position_shift"])}
- Median position shift: {format_number(latest_position["median_position_shift"])}
- Max position shift: {format_number(latest_position["max_position_shift"])}
"""
    else:
        latest_position_section = """
## Latest Consecutive-Run Position Stability

Not enough runs to compare position stability.
"""

    report = f"""# Source Behavior Analysis

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

- Average source-window time span: {format_number(avg_window_span)} minutes
- Latest run source-window time span: {format_number(latest_window["source_window_time_span_minutes"])} minutes
- Latest run oldest review date: {latest_window["min_review_date"]}
- Latest run newest review date: {latest_window["max_review_date"]}

## Date Ordering

This checks whether the returned reviews are strictly ordered from newest to oldest by review timestamp.

### Summary

- Average date-order violation rate: {format_percent(avg_date_order_violation_rate)}

A low violation rate suggests that the source is mostly ordered by review timestamp.
A high violation rate suggests that the source may be affected by ranking, indexing, moderation, or other source-side logic.

{latest_position_section}

## First-Seen Delay

This estimates the delay between a review's source timestamp and the first time it appears in our collected source windows.

### Summary

- Average first-seen delay: {format_number(avg_first_seen_delay)} minutes
- Median first-seen delay: {format_number(median_first_seen_delay)} minutes

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
"""

    MARKDOWN_OUTPUT_PATH.write_text(report, encoding="utf-8")


def main():
    """
    Main workflow for source behavior analysis.
    """
    conn = connect_database()

    try:
        source_df = load_source_window_reviews(conn)

        if source_df.empty:
            print("No source-window records found. Run ingestion first.")
            return

        source_df = parse_datetime_columns(source_df)

        window_span_df = compute_window_date_span(source_df)
        position_stability_df = compute_position_stability(source_df)
        date_order_df = compute_date_order_violations(source_df)
        first_seen_delay_df = compute_first_seen_delay(source_df)

        run_level_summary_df = combine_run_level_metrics(
            window_span_df,
            date_order_df
        )

        write_csv_outputs(
            run_level_summary_df,
            position_stability_df,
            first_seen_delay_df
        )

        write_markdown_report(
            run_level_summary_df,
            position_stability_df,
            first_seen_delay_df
        )

        print("Source behavior analysis generated successfully.")
        print("CSV outputs written to: outputs/source_behavior/")
        print(f"Markdown report written to: {MARKDOWN_OUTPUT_PATH}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
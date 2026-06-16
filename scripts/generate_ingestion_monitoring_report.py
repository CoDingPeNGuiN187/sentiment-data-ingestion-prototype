import sqlite3
from pathlib import Path

import pandas as pd

# File paths

DATABASE_PATH = Path("data/database/reviews.db")

OUTPUT_DIR = Path("outputs/monitoring")
CSV_OUTPUT_PATH = OUTPUT_DIR / "ingestion_monitoring_summary.csv"

DOCS_DIR = Path("docs")
MARKDOWN_OUTPUT_PATH = DOCS_DIR / "ingestion_monitoring_report.md"


# Database connection

def connect_database():
    """
    Connect to the local SQLite database.

    This database should already be created by the ingestion pipeline.
    """
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DATABASE_PATH}. "
            "Run scripts/ingest_google_play_to_sqlite.py first."
        )

    return sqlite3.connect(DATABASE_PATH)


# -----------------------------
# Load data from SQLite
# -----------------------------

def load_ingestion_runs(conn):
    """
    Load run-level metadata from the ingestion_runs table.

    This table tells us whether each run succeeded, how many records were
    collected, inserted, or duplicated, and how long the run took.
    """
    query = """
    SELECT
        ingestion_run_id,
        app_id,
        requested_count,
        collected_count,
        inserted_count,
        duplicate_count,
        runtime_seconds,
        sort_method,
        status,
        started_at,
        completed_at,
        notes
    FROM ingestion_runs
    ORDER BY ingestion_run_id;
    """

    return pd.read_sql_query(query, conn)


def load_source_window_reviews(conn):
    """
    Load full source-window records from source_window_reviews.

    This table stores every review returned by the source for each run,
    including reviews that were already in the database.

    We use it to calculate:
    - source-window overlap
    - source-side freshness based on review_date
    - old-but-new-to-database records
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


# Utility functions

def safe_divide(numerator, denominator):
    """
    Safely divide two numbers.

    If denominator is 0 or missing, return None instead of crashing.
    """
    if denominator is None or pd.isna(denominator) or denominator == 0:
        return None

    if numerator is None or pd.isna(numerator):
        return None

    return numerator / denominator


def parse_datetime_column(series):
    """
    Convert a pandas column into timezone-aware datetime values.

    The ingestion pipeline stores timestamps as ISO strings.
    This function makes comparison safer.
    """
    return pd.to_datetime(series, errors="coerce", utc=True)


def format_percent(value):
    """
    Format decimal values as percentages.

    Example:
    0.988 -> 98.80%
    """
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.2%}"


def format_number(value):
    """
    Format numeric values cleanly for markdown.
    """
    if value is None or pd.isna(value):
        return "N/A"

    if isinstance(value, float):
        return f"{value:.2f}"

    return str(value)


def calculate_source_window_overlap(current_ids, previous_ids):
    """
    Calculate overlap between two consecutive source windows.

    Example:
    - Previous run returned 1000 review IDs.
    - Current run returned 1000 review IDs.
    - 988 review IDs appeared in both windows.

    overlap_rate = 988 / 1000 = 98.8%

    This tells us how much the source window changed between runs.
    """
    if previous_ids is None or len(current_ids) == 0:
        return None, None

    overlap_count = len(current_ids.intersection(previous_ids))
    overlap_rate = overlap_count / len(current_ids)

    return overlap_count, overlap_rate



# Core monitoring calculation

def compute_run_level_monitoring_metrics(runs_df, source_window_df):
    """
    Create one monitoring row per ingestion run.

    This function calculates two types of metrics:

    1. Pipeline health metrics:
       - success/failure status
       - collected records
       - inserted records
       - duplicate records
       - runtime
       - throughput

    2. Source behavior and freshness metrics:
       - source-window overlap rate
       - source-returned duplicate count
       - newly created since previous run time
       - old relative to previous run time
       - old-but-new-to-database count

    Important distinction:
    - inserted_count means the record was new to our database.
    - newly_created_since_previous_run_time_count means the review's source timestamp
      is later than the previous ingestion run's completion time.

    These are not the same.
    """
    monitoring_rows = []

    previous_source_ids = None
    previous_completed_at = None

    # Make datetime parsing explicit.
    runs_df = runs_df.copy()
    source_window_df = source_window_df.copy()

    runs_df["completed_at_parsed"] = parse_datetime_column(runs_df["completed_at"])
    source_window_df["review_date_parsed"] = parse_datetime_column(source_window_df["review_date"])

    for _, run in runs_df.iterrows():
        ingestion_run_id = run["ingestion_run_id"]

        current_source_window = source_window_df[
            source_window_df["ingestion_run_id"] == ingestion_run_id
        ].copy()

        current_source_ids = set(
            current_source_window["platform_review_id"].dropna().astype(str)
        )

        # Basic run-level counts

        collected_count = run["collected_count"] if pd.notna(run["collected_count"]) else 0
        inserted_count = run["inserted_count"] if pd.notna(run["inserted_count"]) else 0
        duplicate_count = run["duplicate_count"] if pd.notna(run["duplicate_count"]) else 0
        runtime_seconds = run["runtime_seconds"] if pd.notna(run["runtime_seconds"]) else 0

        duplicate_rate = safe_divide(duplicate_count, collected_count)
        insert_rate = safe_divide(inserted_count, collected_count)
        throughput_records_per_second = safe_divide(collected_count, runtime_seconds)

        # Ingestion-category counts
        # from source_window_reviews

        category_counts = (
            current_source_window["ingestion_category"]
            .fillna("unknown")
            .value_counts()
            .to_dict()
        )

        ingestion_category_newly_created_count = category_counts.get("newly_created", 0)
        ingestion_category_old_but_new_count = category_counts.get("old_but_new_to_database", 0)
        duplicate_source_window_count = category_counts.get("duplicate", 0)
        initial_load_count = category_counts.get("initial_load", 0)
        unknown_category_count = category_counts.get("unknown", 0)


        # Strict freshness based on time
        # This is the key correction.
        #
        # We compare each returned review's review_date to the previous run's
        # completed_at timestamp.
        #
        # If review_date > previous_completed_at:
        #     the review was genuinely created after the previous ingestion run.
        #
        # If review_date <= previous_completed_at:
        #     the review is old relative to the previous ingestion run,
        #     even if it is new to our database.


        if previous_completed_at is not None and pd.notna(previous_completed_at):
            newly_created_since_previous_run_time_mask = (
                current_source_window["review_date_parsed"] > previous_completed_at
            )

            old_relative_to_previous_run_time_mask = (
                current_source_window["review_date_parsed"].notna()
                & (current_source_window["review_date_parsed"] <= previous_completed_at)
            )

            newly_created_since_previous_run_time_count = int(
                newly_created_since_previous_run_time_mask.sum()
            )

            old_relative_to_previous_run_time_count = int(
                old_relative_to_previous_run_time_mask.sum()
            )

            newly_created_since_previous_run_time_rate = safe_divide(
                newly_created_since_previous_run_time_count,
                collected_count
            )

            old_relative_to_previous_run_time_rate = safe_divide(
                old_relative_to_previous_run_time_count,
                collected_count
            )
        else:
            newly_created_since_previous_run_time_count = None
            old_relative_to_previous_run_time_count = None
            newly_created_since_previous_run_time_rate = None
            old_relative_to_previous_run_time_rate = None

        # -----------------------------
        # Inserted records freshness check
        # -----------------------------
        # This estimates how many inserted records were genuinely fresh
        # relative to the previous ingestion run time.
        #
        # Logic:
        # - A non-duplicate returned record usually corresponds to a record
        #   inserted into reviews.
        # - We use is_existing_review = 0 as "new to database in this run."
        # -----------------------------

        new_to_database_window = current_source_window[
            current_source_window["is_existing_review"] == 0
        ].copy()

        if previous_completed_at is not None and pd.notna(previous_completed_at):
            inserted_and_new_since_previous_run_time_count = int(
                (
                    new_to_database_window["review_date_parsed"] > previous_completed_at
                ).sum()
            )

            inserted_but_old_relative_to_previous_run_time_count = int(
                (
                    new_to_database_window["review_date_parsed"].notna()
                    & (new_to_database_window["review_date_parsed"] <= previous_completed_at)
                ).sum()
            )
        else:
            inserted_and_new_since_previous_run_time_count = None
            inserted_but_old_relative_to_previous_run_time_count = None

        # -----------------------------
        # Source-window overlap
        # -----------------------------

        overlap_count, overlap_rate = calculate_source_window_overlap(
            current_source_ids,
            previous_source_ids
        )

        monitoring_rows.append(
            {
                "ingestion_run_id": ingestion_run_id,
                "app_id": run["app_id"],
                "status": run["status"],
                "started_at": run["started_at"],
                "completed_at": run["completed_at"],
                "previous_run_completed_at": (
                    previous_completed_at.isoformat()
                    if previous_completed_at is not None and pd.notna(previous_completed_at)
                    else None
                ),
                "requested_count": run["requested_count"],
                "collected_count": collected_count,
                "inserted_count": inserted_count,
                "duplicate_count": duplicate_count,
                "duplicate_rate": duplicate_rate,
                "insert_rate": insert_rate,

                # Existing ingestion classification from ingestion script.
                "ingestion_category_newly_created_count": ingestion_category_newly_created_count,
                "ingestion_category_old_but_new_to_database_count": ingestion_category_old_but_new_count,

                # Corrected strict time-based freshness metrics.
                "newly_created_since_previous_run_time_count": newly_created_since_previous_run_time_count,
                "newly_created_since_previous_run_time_rate": newly_created_since_previous_run_time_rate,
                "old_relative_to_previous_run_time_count": old_relative_to_previous_run_time_count,
                "old_relative_to_previous_run_time_rate": old_relative_to_previous_run_time_rate,

                # Inserted-record specific freshness split.
                "inserted_and_new_since_previous_run_time_count": inserted_and_new_since_previous_run_time_count,
                "inserted_but_old_relative_to_previous_run_time_count": inserted_but_old_relative_to_previous_run_time_count,

                # Source-window category counts.
                "duplicate_source_window_count": duplicate_source_window_count,
                "initial_load_count": initial_load_count,
                "unknown_category_count": unknown_category_count,
                "source_window_size": len(current_source_ids),
                "source_window_overlap_count": overlap_count,
                "source_window_overlap_rate": overlap_rate,

                # Performance metrics.
                "runtime_seconds": runtime_seconds,
                "throughput_records_per_second": throughput_records_per_second,
                "sort_method": run["sort_method"],
                "notes": run["notes"],
            }
        )

        previous_source_ids = current_source_ids
        previous_completed_at = run["completed_at_parsed"]

    return pd.DataFrame(monitoring_rows)


# -----------------------------
# Output writers
# -----------------------------

def write_monitoring_csv(monitoring_df):
    """
    Write run-level monitoring metrics to CSV.

    This CSV is useful for:
    - checking historical trends
    - plotting metrics later
    - sharing structured monitoring output
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    monitoring_df.to_csv(CSV_OUTPUT_PATH, index=False)


def write_markdown_report(monitoring_df):
    """
    Write a human-readable monitoring report.

    This report summarizes:
    - pipeline health
    - data collection metrics
    - source freshness metrics
    - warning signals to monitor
    """
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    total_runs = len(monitoring_df)
    successful_runs = (monitoring_df["status"] == "success").sum()
    failed_runs = total_runs - successful_runs

    success_rate = safe_divide(successful_runs, total_runs)
    failure_rate = safe_divide(failed_runs, total_runs)

    avg_collected = monitoring_df["collected_count"].mean()
    avg_inserted = monitoring_df["inserted_count"].mean()
    avg_duplicate_rate = monitoring_df["duplicate_rate"].mean()

    avg_overlap_rate = monitoring_df["source_window_overlap_rate"].dropna().mean()
    avg_runtime = monitoring_df["runtime_seconds"].mean()
    avg_throughput = monitoring_df["throughput_records_per_second"].dropna().mean()

    total_collected = monitoring_df["collected_count"].sum()
    total_inserted = monitoring_df["inserted_count"].sum()
    total_duplicates = monitoring_df["duplicate_count"].sum()

    total_ingestion_category_newly_created = monitoring_df[
        "ingestion_category_newly_created_count"
    ].sum()

    total_ingestion_category_old_but_new = monitoring_df[
        "ingestion_category_old_but_new_to_database_count"
    ].sum()

    total_strict_newly_created = monitoring_df[
        "newly_created_since_previous_run_time_count"
    ].dropna().sum()

    total_inserted_and_new_since_previous_run_time = monitoring_df[
        "inserted_and_new_since_previous_run_time_count"
    ].dropna().sum()

    total_inserted_but_old_relative_to_previous_run_time = monitoring_df[
        "inserted_but_old_relative_to_previous_run_time_count"
    ].dropna().sum()

    latest_run = monitoring_df.iloc[-1] if total_runs > 0 else None

    if latest_run is not None:
        latest_run_section = f"""
## Latest Run Snapshot

- Latest ingestion run ID: {latest_run["ingestion_run_id"]}
- Status: {latest_run["status"]}
- Collected records: {latest_run["collected_count"]}
- Inserted records: {latest_run["inserted_count"]}
- Duplicate rate: {format_percent(latest_run["duplicate_rate"])}
- Source-window overlap rate: {format_percent(latest_run["source_window_overlap_rate"])}
- Ingestion-category newly-created count: {latest_run["ingestion_category_newly_created_count"]}
- Ingestion-category old-but-new-to-database count: {latest_run["ingestion_category_old_but_new_to_database_count"]}
- Newly created since previous run time: {format_number(latest_run["newly_created_since_previous_run_time_count"])}
- Inserted and new since previous run time: {format_number(latest_run["inserted_and_new_since_previous_run_time_count"])}
- Inserted but old relative to previous run time: {format_number(latest_run["inserted_but_old_relative_to_previous_run_time_count"])}
- Runtime: {format_number(latest_run["runtime_seconds"])} seconds
- Throughput: {format_number(latest_run["throughput_records_per_second"])} records/second
"""
    else:
        latest_run_section = """
## Latest Run Snapshot

No ingestion runs found.
"""

    report = f"""# Ingestion Monitoring Report

## Purpose

This report summarizes operational signals for the review ingestion pipeline.

The goal is to understand whether the pipeline would be healthy if it were running unattended in a production-like setting.

The report tracks both pipeline health and source behavior.

## Overall Pipeline Health

- Total ingestion runs: {total_runs}
- Successful runs: {successful_runs}
- Failed runs: {failed_runs}
- Success rate: {format_percent(success_rate)}
- Failure rate: {format_percent(failure_rate)}
- Average runtime: {format_number(avg_runtime)} seconds
- Average throughput: {format_number(avg_throughput)} records/second

## Data Collection Metrics

- Total records collected: {total_collected}
- Total records inserted: {total_inserted}
- Total duplicate records: {total_duplicates}
- Average records collected per run: {format_number(avg_collected)}
- Average records inserted per run: {format_number(avg_inserted)}
- Average duplicate rate: {format_percent(avg_duplicate_rate)}

## Source-Window and Freshness Metrics

- Average source-window overlap rate: {format_percent(avg_overlap_rate)}
- Total ingestion-category newly-created records: {total_ingestion_category_newly_created}
- Total ingestion-category old-but-new-to-database records: {total_ingestion_category_old_but_new}
- Total records newly created since previous run time: {format_number(total_strict_newly_created)}
- Total inserted records that were new since previous run time: {format_number(total_inserted_and_new_since_previous_run_time)}
- Total inserted records that were old relative to previous run time: {format_number(total_inserted_but_old_relative_to_previous_run_time)}

{latest_run_section}

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

- Run-level monitoring CSV: `{CSV_OUTPUT_PATH}`
- Markdown monitoring report: `{MARKDOWN_OUTPUT_PATH}`
"""

    MARKDOWN_OUTPUT_PATH.write_text(report, encoding="utf-8")


# -----------------------------
# Main function
# -----------------------------

def main():
    """
    Main monitoring workflow.

    Steps:
    1. Connect to SQLite database.
    2. Load ingestion run metadata.
    3. Load source-window records.
    4. Compute run-level monitoring metrics.
    5. Write CSV output.
    6. Write Markdown report.
    """
    conn = connect_database()

    try:
        runs_df = load_ingestion_runs(conn)
        source_window_df = load_source_window_reviews(conn)

        if runs_df.empty:
            print("No ingestion runs found. Run the ingestion pipeline first.")
            return

        if source_window_df.empty:
            print("No source-window records found. Run the updated ingestion pipeline first.")
            return

        monitoring_df = compute_run_level_monitoring_metrics(
            runs_df,
            source_window_df
        )

        write_monitoring_csv(monitoring_df)
        write_markdown_report(monitoring_df)

        print("Monitoring report generated successfully.")
        print(f"CSV output: {CSV_OUTPUT_PATH}")
        print(f"Markdown report: {MARKDOWN_OUTPUT_PATH}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
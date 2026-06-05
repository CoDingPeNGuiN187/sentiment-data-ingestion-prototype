import csv
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# Configuration
REPO_ROOT = Path(__file__).resolve().parents[1]

INGEST_SCRIPT = REPO_ROOT / "scripts" / "ingest_google_play_to_sqlite.py"
DATABASE_PATH = REPO_ROOT / "data" / "database" / "reviews.db"

OUTPUT_DIR = REPO_ROOT / "outputs" / "frequency_tests"
OUTPUT_CSV = OUTPUT_DIR / "ingestion_frequency_results.csv"
OUTPUT_MD = REPO_ROOT / "docs" / "ingestion_frequency_test.md"

# Each tuple means: (run label, seconds to wait before this run)
# First run starts immediately.
TEST_PLAN = [
    ("baseline", 0),
    ("1_min_repeat_1", 60),
    ("1_min_repeat_2", 60),
    ("5_min_repeat", 300),
    ("baseline_long_interval_test", 0),
    ("15_min_repeat", 900),
    ("30_min_repeat", 1800),
    ("1_hour_repeat", 3600),]

OUTPUT_CSV = OUTPUT_DIR / "ingestion_frequency_results_15_30_60min.csv"
OUTPUT_MD = REPO_ROOT / "docs" / "ingestion_frequency_test_15_30_60min.md"


# For a very quick local test, you can temporarily use:
# TEST_PLAN = [
#     ("baseline", 0),
#     ("10_sec_repeat_1", 10),
#     ("10_sec_repeat_2", 10),
# ]


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def run_ingestion_script():
    """
    Run the existing single-run ingestion script.
    This script should create one new row in ingestion_runs.
    """
    result = subprocess.run(
        [sys.executable, str(INGEST_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    return {
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def get_latest_ingestion_run():
    """
    Read the latest ingestion run result from SQLite.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            ingestion_run_id,
            requested_count,
            collected_count,
            inserted_count,
            duplicate_count,
            runtime_seconds,
            status,
            started_at,
            completed_at,
            notes
        FROM ingestion_runs
        ORDER BY ingestion_run_id DESC
        LIMIT 1;
        """
    )

    run = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) AS total_reviews FROM reviews;")
    total_reviews = cursor.fetchone()["total_reviews"]

    conn.close()

    if run is None:
        return None

    return {
        "ingestion_run_id": run["ingestion_run_id"],
        "requested_count": run["requested_count"],
        "collected_count": run["collected_count"],
        "inserted_count": run["inserted_count"],
        "duplicate_count": run["duplicate_count"],
        "runtime_seconds": run["runtime_seconds"],
        "status": run["status"],
        "started_at": run["started_at"],
        "completed_at": run["completed_at"],
        "notes": run["notes"],
        "total_reviews_after_run": total_reviews,
    }


def compute_rates(row):
    """
    Add duplicate_rate and new_review_rate.
    """
    collected = row.get("collected_count") or 0
    inserted = row.get("inserted_count") or 0
    duplicates = row.get("duplicate_count") or 0

    if collected == 0:
        row["duplicate_rate"] = None
        row["new_review_rate"] = None
    else:
        row["duplicate_rate"] = round(duplicates / collected, 4)
        row["new_review_rate"] = round(inserted / collected, 4)

    return row


def write_csv(results):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "test_label",
        "wait_before_run_seconds",
        "test_started_at",
        "test_completed_at",
        "subprocess_return_code",
        "ingestion_run_id",
        "requested_count",
        "collected_count",
        "inserted_count",
        "duplicate_count",
        "duplicate_rate",
        "new_review_rate",
        "runtime_seconds",
        "status",
        "total_reviews_after_run",
        "started_at",
        "completed_at",
        "notes",
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in results:
            writer.writerow({key: row.get(key) for key in fieldnames})


def write_markdown(results):
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write("# Ingestion Frequency Test\n\n")

        f.write("## Goal\n\n")
        f.write(
            "Test how the Google Play to SQLite ingestion prototype behaves "
            "when the collection process is run repeatedly at short intervals.\n\n"
        )

        f.write("## Test Setup\n\n")
        f.write("- Source: Google Play Store\n")
        f.write("- App: ChatGPT (`com.openai.chatgpt`)\n")
        f.write("- Database: SQLite\n")
        f.write("- Batch size: configured in `scripts/ingest_google_play_to_sqlite.py`\n")
        f.write("- Deduplication key: `(app_id, platform_review_id)`\n\n")

        f.write("## Metrics Tracked\n\n")
        f.write("- Requested reviews\n")
        f.write("- Collected reviews\n")
        f.write("- Inserted reviews\n")
        f.write("- Duplicate reviews skipped\n")
        f.write("- Duplicate rate\n")
        f.write("- New review rate\n")
        f.write("- Runtime\n")
        f.write("- Database total review count after each run\n")
        f.write("- Run status / errors\n\n")

        f.write("## Results\n\n")
        f.write(
            "| Run | Wait Before Run | Collected | Inserted | Duplicates | "
            "Duplicate Rate | New Review Rate | Runtime | Total Reviews After Run | Status |\n"
        )
        f.write(
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|\n"
        )

        for row in results:
            f.write(
                f"| {row.get('test_label')} "
                f"| {row.get('wait_before_run_seconds')}s "
                f"| {row.get('collected_count')} "
                f"| {row.get('inserted_count')} "
                f"| {row.get('duplicate_count')} "
                f"| {row.get('duplicate_rate')} "
                f"| {row.get('new_review_rate')} "
                f"| {row.get('runtime_seconds')}s "
                f"| {row.get('total_reviews_after_run')} "
                f"| {row.get('status')} |\n"
            )

        f.write("\n## Initial Observations\n\n")
        f.write(
            "TBD. After running the test, summarize whether repeated ingestion "
            "mostly produced new reviews or duplicates, whether runtime changed, "
            "and whether any source-side or database-side issues appeared.\n"
        )


def main():
    if not INGEST_SCRIPT.exists():
        raise FileNotFoundError(f"Ingestion script not found: {INGEST_SCRIPT}")

    results = []

    print("Starting ingestion frequency test...")
    print(f"Ingestion script: {INGEST_SCRIPT}")
    print(f"Database path: {DATABASE_PATH}")
    print()

    for test_label, wait_seconds in TEST_PLAN:
        if wait_seconds > 0:
            print(f"Waiting {wait_seconds} seconds before run: {test_label}")
            time.sleep(wait_seconds)

        print(f"\nRunning ingestion test: {test_label}")
        test_started_at = utc_now_iso()

        process_result = run_ingestion_script()

        test_completed_at = utc_now_iso()

        if process_result["return_code"] != 0:
            print("Ingestion script returned a non-zero exit code.")
            print(process_result["stderr"])

        latest_run = get_latest_ingestion_run()

        if latest_run is None:
            row = {
                "test_label": test_label,
                "wait_before_run_seconds": wait_seconds,
                "test_started_at": test_started_at,
                "test_completed_at": test_completed_at,
                "subprocess_return_code": process_result["return_code"],
                "status": "no_ingestion_run_found",
            }
        else:
            row = {
                "test_label": test_label,
                "wait_before_run_seconds": wait_seconds,
                "test_started_at": test_started_at,
                "test_completed_at": test_completed_at,
                "subprocess_return_code": process_result["return_code"],
                **latest_run,
            }

            row = compute_rates(row)

        results.append(row)

        print(
            f"Result: collected={row.get('collected_count')}, "
            f"inserted={row.get('inserted_count')}, "
            f"duplicates={row.get('duplicate_count')}, "
            f"runtime={row.get('runtime_seconds')}s, "
            f"status={row.get('status')}"
        )

    write_csv(results)
    write_markdown(results)

    print("\nFrequency test complete.")
    print(f"CSV results written to: {OUTPUT_CSV}")
    print(f"Markdown summary written to: {OUTPUT_MD}")


if __name__ == "__main__":
    main()
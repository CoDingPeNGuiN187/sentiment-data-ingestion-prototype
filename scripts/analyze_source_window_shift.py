import sqlite3
from pathlib import Path


DATABASE_PATH = Path("data/database/reviews.db")


def connect_database():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_latest_two_runs(conn):
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT ingestion_run_id, started_at, completed_at
        FROM ingestion_runs
        WHERE status = 'success'
        ORDER BY ingestion_run_id DESC
        LIMIT 2;
        """
    )

    rows = cursor.fetchall()

    if len(rows) < 2:
        return None, None

    latest_run = rows[0]
    previous_run = rows[1]

    return previous_run, latest_run


def get_source_window_ids(conn, ingestion_run_id):
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT platform_review_id
        FROM source_window_reviews
        WHERE ingestion_run_id = ?;
        """,
        (ingestion_run_id,),
    )

    return {row["platform_review_id"] for row in cursor.fetchall()}


def get_source_window_date_range(conn, ingestion_run_id):
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            MIN(review_date) AS min_review_date,
            MAX(review_date) AS max_review_date,
            COUNT(*) AS returned_count
        FROM source_window_reviews
        WHERE ingestion_run_id = ?;
        """,
        (ingestion_run_id,),
    )

    return cursor.fetchone()


def get_inserted_freshness_summary(conn, latest_run_id, previous_completed_at):
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            COUNT(*) AS inserted_count,
            SUM(CASE WHEN review_date > ? THEN 1 ELSE 0 END) AS newly_created_count,
            SUM(CASE WHEN review_date <= ? THEN 1 ELSE 0 END) AS old_but_new_count,
            MIN(review_date) AS min_inserted_review_date,
            MAX(review_date) AS max_inserted_review_date
        FROM reviews
        WHERE ingestion_run_id = ?;
        """,
        (
            previous_completed_at,
            previous_completed_at,
            latest_run_id,
        ),
    )

    return cursor.fetchone()


def main():
    conn = connect_database()

    previous_run, latest_run = get_latest_two_runs(conn)

    if previous_run is None or latest_run is None:
        print("Need at least two successful ingestion runs to analyze source window shift.")
        conn.close()
        return

    previous_run_id = previous_run["ingestion_run_id"]
    latest_run_id = latest_run["ingestion_run_id"]

    previous_ids = get_source_window_ids(conn, previous_run_id)
    latest_ids = get_source_window_ids(conn, latest_run_id)

    overlap_ids = previous_ids.intersection(latest_ids)

    previous_window = get_source_window_date_range(conn, previous_run_id)
    latest_window = get_source_window_date_range(conn, latest_run_id)

    freshness = get_inserted_freshness_summary(
        conn=conn,
        latest_run_id=latest_run_id,
        previous_completed_at=previous_run["completed_at"],
    )

    previous_count = len(previous_ids)
    latest_count = len(latest_ids)
    overlap_count = len(overlap_ids)

    overlap_rate = overlap_count / latest_count if latest_count > 0 else 0

    print("Source Window Shift Analysis")
    print("----------------------------")
    print(f"Previous run ID: {previous_run_id}")
    print(f"Latest run ID: {latest_run_id}")
    print()
    print("Source window overlap:")
    print(f"- Previous returned count: {previous_count}")
    print(f"- Latest returned count: {latest_count}")
    print(f"- Overlap count: {overlap_count}")
    print(f"- Overlap rate vs latest window: {overlap_rate:.2%}")
    print()
    print("Previous source window date range:")
    print(f"- Min review date: {previous_window['min_review_date']}")
    print(f"- Max review date: {previous_window['max_review_date']}")
    print()
    print("Latest source window date range:")
    print(f"- Min review date: {latest_window['min_review_date']}")
    print(f"- Max review date: {latest_window['max_review_date']}")
    print()
    print("Freshness of newly inserted database records in latest run:")
    print(f"- Inserted count: {freshness['inserted_count']}")
    print(f"- Newly created since previous run: {freshness['newly_created_count']}")
    print(f"- Old but new to database: {freshness['old_but_new_count']}")
    print(f"- Min inserted review date: {freshness['min_inserted_review_date']}")
    print(f"- Max inserted review date: {freshness['max_inserted_review_date']}")

    if freshness["old_but_new_count"] and freshness["old_but_new_count"] > 0:
        print()
        print("Interpretation:")
        print(
            "Some reviews were new to the database but older than the previous "
            "run completion time. This suggests a shifted source window may be present."
        )

    conn.close()


if __name__ == "__main__":
    main()
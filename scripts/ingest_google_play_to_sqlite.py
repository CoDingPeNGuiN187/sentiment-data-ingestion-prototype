import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from google_play_scraper import reviews, Sort

# Configuration
APP_NAME = "ChatGPT"
PLATFORM = "Google Play"
PLATFORM_APP_ID = "com.openai.chatgpt"

COUNTRY = "us"
LANGUAGE = "en"
NUM_REVIEWS = 1000

DATABASE_PATH = Path("data/database/reviews.db")
SCHEMA_PATH = Path("sql/schema_sqlite.sql")


# Helper functions
def utc_now_iso():
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def connect_database():
    """Create database folder and connect to SQLite database."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def initialize_database(conn):
    """Create tables using schema_sqlite.sql."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn.executescript(schema_sql)
    conn.commit()


def get_or_create_app(conn):
    """
    Insert app metadata if it does not already exist.
    Return internal app_id from apps table.
    """
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO apps (
            platform,
            platform_app_id,
            app_name,
            country,
            language
        )
        VALUES (?, ?, ?, ?, ?);
        """,
        (
            PLATFORM,
            PLATFORM_APP_ID,
            APP_NAME,
            COUNTRY,
            LANGUAGE,
        ),
    )

    cursor.execute(
        """
        SELECT app_id
        FROM apps
        WHERE platform = ?
          AND platform_app_id = ?
          AND country = ?
          AND language = ?;
        """,
        (
            PLATFORM,
            PLATFORM_APP_ID,
            COUNTRY,
            LANGUAGE,
        ),
    )

    app_id = cursor.fetchone()[0]
    conn.commit()

    return app_id


def create_ingestion_run(conn, app_id, started_at):
    """
    Create a new ingestion run record.
    At this point collected_count and inserted_count are unknown,
    so they will be updated after review insertion.
    """
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO ingestion_runs (
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
        )
        VALUES (?, ?, NULL, NULL, NULL, NULL, ?, ?, ?, NULL, NULL);
        """,
        (
            app_id,
            NUM_REVIEWS,
            "newest",
            "running",
            started_at,
        ),
    )

    ingestion_run_id = cursor.lastrowid
    conn.commit()

    return ingestion_run_id


def fetch_google_play_reviews():
    """Fetch reviews from Google Play."""
    result, continuation_token = reviews(
        PLATFORM_APP_ID,
        lang=LANGUAGE,
        country=COUNTRY,
        sort=Sort.NEWEST,
        count=NUM_REVIEWS,
    )

    return result


def is_generic_text(text):
    """Return True if review text is generic and low-information."""
    generic_terms = {
        "good",
        "great",
        "nice",
        "bad",
        "ok",
        "okay",
        "excellent",
        "awesome",
        "amazing",
        "perfect",
        "love it",
        "cool",
        "best",
        "very good",
    }

    cleaned = text.strip().lower()
    return cleaned in generic_terms


def compute_quality_features(review_text, duplicate_text_set):
    """
    Compute simple review quality features.
    This is a first-pass rule-based version.
    """
    clean_text = review_text.strip()
    words = clean_text.split()

    review_char_length = len(clean_text)
    review_word_count = len(words)

    is_very_short = review_word_count <= 2
    generic = is_generic_text(clean_text)
    is_low_signal = is_very_short or generic
    is_duplicate_text = clean_text.lower() in duplicate_text_set

    return {
        "review_char_length": review_char_length,
        "review_word_count": review_word_count,
        "is_very_short": is_very_short,
        "is_generic_text": generic,
        "is_low_signal": is_low_signal,
        "is_duplicate_text": is_duplicate_text,
        "detected_language": None,
    }


def insert_reviews_and_quality_features(conn, app_id, ingestion_run_id, raw_reviews, collected_at):
    """
    Insert reviews into reviews table.
    Insert quality features into review_quality_features table.
    Skip duplicate reviews based on UNIQUE(app_id, platform_review_id).
    """
    cursor = conn.cursor()

    inserted_count = 0
    duplicate_count = 0

    seen_texts = set()

    for r in raw_reviews:
        platform_review_id = r.get("reviewId")
        review_text = r.get("content")

        if platform_review_id is None or review_text is None:
            continue

        review_text_clean = review_text.strip()
        duplicate_text_set = seen_texts.copy()

        try:
            cursor.execute(
                """
                INSERT INTO reviews (
                    app_id,
                    ingestion_run_id,
                    platform_review_id,
                    review_text,
                    rating,
                    review_date,
                    app_version,
                    thumbs_up_count,
                    developer_response,
                    collected_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    app_id,
                    ingestion_run_id,
                    platform_review_id,
                    review_text,
                    r.get("score"),
                    str(r.get("at")) if r.get("at") is not None else None,
                    r.get("reviewCreatedVersion"),
                    r.get("thumbsUpCount"),
                    r.get("replyContent"),
                    collected_at,
                ),
            )

            review_id = cursor.lastrowid
            inserted_count += 1

            quality = compute_quality_features(
                review_text=review_text_clean,
                duplicate_text_set=duplicate_text_set,
            )

            cursor.execute(
                """
                INSERT INTO review_quality_features (
                    review_id,
                    review_char_length,
                    review_word_count,
                    is_very_short,
                    is_generic_text,
                    is_low_signal,
                    is_duplicate_text,
                    detected_language
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    review_id,
                    quality["review_char_length"],
                    quality["review_word_count"],
                    int(quality["is_very_short"]),
                    int(quality["is_generic_text"]),
                    int(quality["is_low_signal"]),
                    int(quality["is_duplicate_text"]),
                    quality["detected_language"],
                ),
            )

        except sqlite3.IntegrityError:
            # This usually means duplicate platform_review_id for the same app.
            duplicate_count += 1

        seen_texts.add(review_text_clean.lower())

    conn.commit()

    return inserted_count, duplicate_count


def update_ingestion_run(
    conn,
    ingestion_run_id,
    collected_count,
    inserted_count,
    duplicate_count,
    runtime_seconds,
    completed_at,
    status,
    notes,
):
    """Update ingestion run after collection and insertion finish."""
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE ingestion_runs
        SET collected_count = ?,
            inserted_count = ?,
            duplicate_count = ?,
            runtime_seconds = ?,
            completed_at = ?,
            status = ?,
            notes = ?
        WHERE ingestion_run_id = ?;
        """,
        (
            collected_count,
            inserted_count,
            duplicate_count,
            runtime_seconds,
            completed_at,
            status,
            notes,
            ingestion_run_id,
        ),
    )

    conn.commit()


def print_database_summary(conn):
    """Print simple database row counts after ingestion."""
    cursor = conn.cursor()

    tables = [
        "apps",
        "ingestion_runs",
        "reviews",
        "review_quality_features",
    ]

    print("\nDatabase summary:")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table};")
        count = cursor.fetchone()[0]
        print(f"- {table}: {count} rows")


# Main end-to-end prototype
def main():
    start_time = time.time()
    started_at = utc_now_iso()
    collected_at = started_at

    print("Starting Google Play to SQLite ingestion prototype...")
    print(f"App: {APP_NAME}")
    print(f"Platform app ID: {PLATFORM_APP_ID}")
    print(f"Country: {COUNTRY}")
    print(f"Language: {LANGUAGE}")
    print(f"Requested reviews: {NUM_REVIEWS}")
    print(f"Database path: {DATABASE_PATH}")

    conn = connect_database()

    try:
        initialize_database(conn)

        app_id = get_or_create_app(conn)

        ingestion_run_id = create_ingestion_run(
            conn=conn,
            app_id=app_id,
            started_at=started_at,
        )

        raw_reviews = fetch_google_play_reviews()
        collected_count = len(raw_reviews)

        inserted_count, duplicate_count = insert_reviews_and_quality_features(
            conn=conn,
            app_id=app_id,
            ingestion_run_id=ingestion_run_id,
            raw_reviews=raw_reviews,
            collected_at=collected_at,
        )

        end_time = time.time()
        completed_at = utc_now_iso()
        runtime_seconds = round(end_time - start_time, 2)

        status = "success"
        notes = "Initial end-to-end prototype run from Google Play scraper to SQLite database."

        update_ingestion_run(
            conn=conn,
            ingestion_run_id=ingestion_run_id,
            collected_count=collected_count,
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
            runtime_seconds=runtime_seconds,
            completed_at=completed_at,
            status=status,
            notes=notes,
        )

        print("\nIngestion complete.")
        print(f"Collected reviews: {collected_count}")
        print(f"Inserted reviews: {inserted_count}")
        print(f"Duplicate reviews skipped: {duplicate_count}")
        print(f"Runtime: {runtime_seconds} seconds")

        print_database_summary(conn)

    except Exception as e:
        end_time = time.time()
        completed_at = utc_now_iso()
        runtime_seconds = round(end_time - start_time, 2)

        print("\nIngestion failed.")
        print(f"Error message: {e}")

        # Try to update the latest ingestion run if it exists
        try:
            update_ingestion_run(
                conn=conn,
                ingestion_run_id=ingestion_run_id,
                collected_count=0,
                inserted_count=0,
                duplicate_count=0,
                runtime_seconds=runtime_seconds,
                completed_at=completed_at,
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass

    finally:
        conn.close()


if __name__ == "__main__":
    main()
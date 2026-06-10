import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from google_play_scraper import reviews, Sort


# -----------------------------
# Configuration
# -----------------------------
APP_NAME = "ChatGPT"
PLATFORM = "Google Play"
PLATFORM_APP_ID = "com.openai.chatgpt"

COUNTRY = "us"
LANGUAGE = "en"
NUM_REVIEWS = 1000

DATABASE_PATH = Path("data/database/reviews.db")
SCHEMA_PATH = Path("sql/schema_sqlite.sql")


# -----------------------------
# Time helper functions
# -----------------------------
def utc_now_iso():
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def normalize_datetime_to_utc_iso(value):
    """
    Normalize datetime values to UTC ISO format for consistent database storage.

    google-play-scraper usually returns a Python datetime object for review_date.
    If the datetime is timezone-naive, this prototype treats it as UTC.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)

        return value.isoformat()

    return str(value)


def parse_datetime_safe(value):
    """
    Parse datetime string into a timezone-aware UTC datetime object.

    Supports ISO strings and older SQLite-style strings.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()

        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            try:
                dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt


# -----------------------------
# Database setup
# -----------------------------
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

    result = cursor.fetchone()

    if result is None:
        raise RuntimeError("Failed to create or retrieve app record.")

    app_id = result[0]
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


# -----------------------------
# Source extraction
# -----------------------------
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


# -----------------------------
# Freshness classification helpers
# -----------------------------
def get_previous_watermark_review_date(conn):
    """
    Return the maximum review_date already stored in the reviews table
    before the current ingestion run inserts new records.

    This acts as a simple freshness watermark.
    """
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT MAX(review_date)
        FROM reviews;
        """
    )

    result = cursor.fetchone()[0]
    return result


def review_exists(conn, app_id, platform_review_id):
    """
    Return True if this platform review ID already exists
    in the main reviews table.
    """
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT 1
        FROM reviews
        WHERE app_id = ?
          AND platform_review_id = ?
        LIMIT 1;
        """,
        (app_id, platform_review_id),
    )

    return cursor.fetchone() is not None


def classify_source_review(
    conn,
    app_id,
    platform_review_id,
    review_date_iso,
    previous_watermark_iso,
):
    """
    Classify a returned source review into one of four categories:

    - initial_load:
        The database has no previous watermark yet.
    - duplicate:
        The platform_review_id already exists in the reviews table.
    - newly_created:
        The review is new to the database and its review_date is later than
        the previous watermark.
    - old_but_new_to_database:
        The review is new to the database, but its review_date is not later
        than the previous watermark. This may indicate a shifted source window.
    """
    if review_exists(conn, app_id, platform_review_id):
        return {
            "ingestion_category": "duplicate",
            "is_existing_review": 1,
            "is_newly_created": 0,
            "is_old_but_new_to_database": 0,
        }

    watermark_dt = parse_datetime_safe(previous_watermark_iso)
    review_dt = parse_datetime_safe(review_date_iso)

    if watermark_dt is None:
        return {
            "ingestion_category": "initial_load",
            "is_existing_review": 0,
            "is_newly_created": 0,
            "is_old_but_new_to_database": 0,
        }

    if review_dt is not None and review_dt > watermark_dt:
        return {
            "ingestion_category": "newly_created",
            "is_existing_review": 0,
            "is_newly_created": 1,
            "is_old_but_new_to_database": 0,
        }

    return {
        "ingestion_category": "old_but_new_to_database",
        "is_existing_review": 0,
        "is_newly_created": 0,
        "is_old_but_new_to_database": 1,
    }


def record_source_window_reviews(
    conn,
    app_id,
    ingestion_run_id,
    raw_reviews,
    collected_at,
    previous_watermark_review_date,
):
    """
    Record every review returned by the source for this ingestion run.

    This table tracks the full returned source window, including:
    - reviews already in the database
    - reviews newly created after the previous watermark
    - old reviews that are new to the database because the source window shifted
    """
    cursor = conn.cursor()

    inserted_source_window_rows = 0

    category_counts = {
        "initial_load": 0,
        "duplicate": 0,
        "newly_created": 0,
        "old_but_new_to_database": 0,
    }

    for position, r in enumerate(raw_reviews):
        platform_review_id = r.get("reviewId")

        if platform_review_id is None:
            continue

        review_date_iso = normalize_datetime_to_utc_iso(r.get("at"))

        classification = classify_source_review(
            conn=conn,
            app_id=app_id,
            platform_review_id=platform_review_id,
            review_date_iso=review_date_iso,
            previous_watermark_iso=previous_watermark_review_date,
        )

        category = classification["ingestion_category"]
        category_counts[category] += 1

        cursor.execute(
            """
            INSERT OR IGNORE INTO source_window_reviews (
                ingestion_run_id,
                app_id,
                platform_review_id,
                review_date,
                returned_position,
                collected_at,
                ingestion_category,
                is_existing_review,
                is_newly_created,
                is_old_but_new_to_database,
                previous_watermark_review_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                ingestion_run_id,
                app_id,
                platform_review_id,
                review_date_iso,
                position,
                collected_at,
                classification["ingestion_category"],
                classification["is_existing_review"],
                classification["is_newly_created"],
                classification["is_old_but_new_to_database"],
                previous_watermark_review_date,
            ),
        )

        if cursor.rowcount == 1:
            inserted_source_window_rows += 1

    conn.commit()

    return inserted_source_window_rows, category_counts


# -----------------------------
# Review quality features
# -----------------------------
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


# -----------------------------
# Loading into main review tables
# -----------------------------
def insert_reviews_and_quality_features(
    conn,
    app_id,
    ingestion_run_id,
    raw_reviews,
    collected_at,
):
    """
    Insert new reviews into the reviews table and insert review quality features.

    Duplicate reviews are skipped using the database-level
    UNIQUE(app_id, platform_review_id) constraint.
    """
    cursor = conn.cursor()

    inserted_count = 0
    duplicate_count = 0
    skipped_count = 0

    seen_texts = set()

    for r in raw_reviews:
        platform_review_id = r.get("reviewId")
        review_text = r.get("content")

        if platform_review_id is None or review_text is None:
            skipped_count += 1
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
                    normalize_datetime_to_utc_iso(r.get("at")),
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
            duplicate_count += 1

        seen_texts.add(review_text_clean.lower())

    conn.commit()

    return inserted_count, duplicate_count, skipped_count


def print_database_summary(conn):
    """Print simple database row counts after ingestion."""
    cursor = conn.cursor()

    tables = [
        "apps",
        "ingestion_runs",
        "reviews",
        "review_quality_features",
        "source_window_reviews",
    ]

    print("\nDatabase summary:")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table};")
        count = cursor.fetchone()[0]
        print(f"- {table}: {count} rows")


# -----------------------------
# Main end-to-end prototype
# -----------------------------
def main():
    start_time = time.time()
    started_at = utc_now_iso()
    collected_at = started_at

    conn = None
    ingestion_run_id = None

    print("Starting Google Play to SQLite ingestion prototype...")
    print(f"App: {APP_NAME}")
    print(f"Platform app ID: {PLATFORM_APP_ID}")
    print(f"Country: {COUNTRY}")
    print(f"Language: {LANGUAGE}")
    print(f"Requested reviews: {NUM_REVIEWS}")
    print(f"Database path: {DATABASE_PATH}")

    try:
        conn = connect_database()
        initialize_database(conn)

        app_id = get_or_create_app(conn)

        ingestion_run_id = create_ingestion_run(
            conn=conn,
            app_id=app_id,
            started_at=started_at,
        )

        previous_watermark_review_date = get_previous_watermark_review_date(conn)

        raw_reviews = fetch_google_play_reviews()
        collected_count = len(raw_reviews)

        source_window_rows, category_counts = record_source_window_reviews(
            conn=conn,
            app_id=app_id,
            ingestion_run_id=ingestion_run_id,
            raw_reviews=raw_reviews,
            collected_at=collected_at,
            previous_watermark_review_date=previous_watermark_review_date,
        )

        inserted_count, duplicate_count, skipped_count = insert_reviews_and_quality_features(
            conn=conn,
            app_id=app_id,
            ingestion_run_id=ingestion_run_id,
            raw_reviews=raw_reviews,
            collected_at=collected_at,
        )

        completed_at = utc_now_iso()
        runtime_seconds = round(time.time() - start_time, 2)

        status = "success"
        notes = (
            "End-to-end prototype run from Google Play scraper to SQLite database. "
            "Recorded source window and classified returned reviews into "
            "initial_load, duplicate, newly_created, and old_but_new_to_database."
        )

        if skipped_count > 0:
            notes += f" Skipped {skipped_count} records with missing review ID or text."

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
        print(f"Source window rows recorded: {source_window_rows}")
        print(f"Inserted reviews: {inserted_count}")
        print(f"Duplicate reviews skipped: {duplicate_count}")
        print(f"Malformed records skipped: {skipped_count}")
        print(f"Runtime: {runtime_seconds} seconds")

        print("\nSource window category counts:")
        print(f"- initial_load: {category_counts['initial_load']}")
        print(f"- duplicate: {category_counts['duplicate']}")
        print(f"- newly_created: {category_counts['newly_created']}")
        print(f"- old_but_new_to_database: {category_counts['old_but_new_to_database']}")

        print_database_summary(conn)

    except Exception as e:
        completed_at = utc_now_iso()
        runtime_seconds = round(time.time() - start_time, 2)

        print("\nIngestion failed.")
        print(f"Error message: {e}")

        if conn is not None and ingestion_run_id is not None:
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
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
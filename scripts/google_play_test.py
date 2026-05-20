from google_play_scraper import reviews, Sort
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
import time

APP_ID = "com.spotify.music"  # Example: Duolingo on Google Play
APP_NAME = "Spotify"
COUNTRY = "us"
LANGUAGE = "en"
NUM_REVIEWS = 2000

OUTPUT_PATH = Path("data/sample/google_play_duolingo_sample.csv")


def print_missing_summary(df: pd.DataFrame) -> None:
    """Print missing-value count and percentage for each column."""
    if df.empty:
        print("No data collected, so missing-value summary is unavailable.")
        return

    missing_count = df.isna().sum()
    missing_percent = (df.isna().mean() * 100).round(2)

    print("\nMissing field summary:")
    for col in df.columns:
        print(f"- {col}: {missing_count[col]} missing ({missing_percent[col]}%)")


def main():
    start_time = time.time()
    collected_at = datetime.now(timezone.utc).isoformat()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    columns = [
        "source_platform",
        "app_name",
        "app_id",
        "country",
        "language",
        "review_id",
        "review_text",
        "rating",
        "review_date",
        "app_version",
        "thumbs_up_count",
        "developer_response",
        "collected_at",
    ]

    rows = []

    print("Starting Google Play review collection...")
    print(f"App name: {APP_NAME}")
    print(f"App ID: {APP_ID}")
    print(f"Country: {COUNTRY}")
    print(f"Language: {LANGUAGE}")
    print(f"Number of reviews requested: {NUM_REVIEWS}")

    try:
        result, continuation_token = reviews(
            APP_ID,
            lang=LANGUAGE,
            country=COUNTRY,
            sort=Sort.NEWEST,
            count=NUM_REVIEWS,
        )

        for r in result:
            rows.append({
                "source_platform": "Google Play",
                "app_name": APP_NAME,
                "app_id": APP_ID,
                "country": COUNTRY,
                "language": LANGUAGE,
                "review_id": r.get("reviewId"),
                "review_text": r.get("content"),
                "rating": r.get("score"),
                "review_date": r.get("at"),
                "app_version": r.get("reviewCreatedVersion"),
                "thumbs_up_count": r.get("thumbsUpCount"),
                "developer_response": r.get("replyContent"),
                "collected_at": collected_at,
            })

    except Exception as e:
        print("Google Play review collection failed.")
        print(f"Error message: {e}")

    df = pd.DataFrame(rows, columns=columns)
    df.to_csv(OUTPUT_PATH, index=False)

    end_time = time.time()
    runtime_seconds = end_time - start_time

    print()
    print(f"Requested reviews: {NUM_REVIEWS}")
    print(f"Collected reviews: {len(df)}")
    print(f"Saved to: {OUTPUT_PATH}")
    print(f"Runtime: {runtime_seconds:.2f} seconds")

    print_missing_summary(df)

    if df.empty:
        print("\nNo reviews were collected.")
        return

    preview_cols = [
        "rating",
        "review_date",
        "app_version",
        "thumbs_up_count",
        "review_text",
    ]

    print("\nPreview:")
    print(df[preview_cols].head(10).to_string(index=False))


if __name__ == "__main__":
    main()

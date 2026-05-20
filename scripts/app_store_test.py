from app_store_web_scraper import AppStoreEntry
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
import time

# -----------------------------
# Configuration
# -----------------------------
APP_ID = 324684580  # App id on Apple App Store
APP_NAME = "Spotify"
COUNTRY = "us"
NUM_REVIEWS = 1000

OUTPUT_PATH = Path("data/sample/app_store_duolingo_sample.csv")


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
        "review_id",
        "review_title",
        "review_text",
        "rating",
        "review_date",
        "user_name",
        "collected_at",
    ]

    rows = []

    print("Starting Apple App Store review collection...")
    print(f"App name: {APP_NAME}")
    print(f"App ID: {APP_ID}")
    print(f"Country: {COUNTRY}")
    print(f"Number of reviews requested: {NUM_REVIEWS}")

    try:
        app = AppStoreEntry(
            app_id=APP_ID,
            country=COUNTRY,
        )

        for review in app.reviews(limit=NUM_REVIEWS):
            rows.append({
                "source_platform": "Apple App Store",
                "app_name": APP_NAME,
                "app_id": APP_ID,
                "country": COUNTRY,
                "review_id": getattr(review, "id", None),
                "review_title": getattr(review, "title", None),
                "review_text": getattr(review, "review", None),
                "rating": getattr(review, "rating", None),
                "review_date": getattr(review, "date", None),
                "user_name": getattr(review, "user_name", None),
                "collected_at": collected_at,
            })

    except Exception as e:
        print("Apple App Store review collection failed.")
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
        print("Possible reasons:")
        print("- The scraper package may be unstable.")
        print("- Apple may have returned an unexpected response format.")
        print("- The app ID or country may need to be checked.")
        print("- Apple App Store collection may require a different access method.")
        return

    preview_cols = [
        "rating",
        "review_date",
        "review_title",
        "review_text",
    ]

    print("\nPreview:")
    print(df[preview_cols].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
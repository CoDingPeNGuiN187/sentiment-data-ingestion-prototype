from google_play_scraper import reviews, Sort
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
import time


# Configuration
APP_ID = "com.openai.chatgpt"
APP_NAME = "ChatGPT"
COUNTRY = "us"
LANGUAGE = "en"
NUM_REVIEWS = 25000

OUTPUT_PATH = Path("data/raw/google_play_chatgpt_25k.csv")
SUMMARY_PATH = Path("docs/google_play_chatgpt_25k_summary.md")


# Helper functions
def print_missing_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return and print missing-value count and percentage for each column."""
    missing_df = pd.DataFrame({
        "missing_count": df.isna().sum(),
        "missing_percent": (df.isna().mean() * 100).round(2)
    })

    print("\nMissing field summary:")
    print(missing_df.to_string())

    return missing_df


def add_review_length_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add review length columns for exploratory analysis."""
    df["review_text_clean"] = df["review_text"].fillna("").astype(str).str.strip()
    df["review_char_length"] = df["review_text_clean"].str.len()
    df["review_word_count"] = df["review_text_clean"].str.split().str.len()
    return df


def identify_low_signal_reviews(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mark low-signal reviews.
    Low-signal here means very short reviews, emoji-only/near-empty reviews,
    or generic one-word comments.
    """
    generic_terms = {
        "good", "great", "nice", "bad", "ok", "okay", "excellent",
        "awesome", "amazing", "perfect", "love it", "cool", "best"
    }

    df["is_very_short"] = df["review_word_count"] <= 2
    df["is_generic_text"] = df["review_text_clean"].str.lower().isin(generic_terms)
    df["is_low_signal"] = df["is_very_short"] | df["is_generic_text"]

    return df


def write_summary_markdown(
    df: pd.DataFrame,
    missing_df: pd.DataFrame,
    runtime_seconds: float,
    duplicate_count: int,
) -> None:
    """Write a markdown summary of the collection and basic EDA results."""
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)

    rating_distribution = df["rating"].value_counts(dropna=False).sort_index()
    app_version_top = df["app_version"].value_counts(dropna=False).head(10)

    review_length_summary = df[[
        "review_char_length",
        "review_word_count"
    ]].describe().round(2)

    low_signal_count = int(df["is_low_signal"].sum())
    low_signal_percent = round(low_signal_count / len(df) * 100, 2) if len(df) > 0 else 0

    date_min = df["review_date"].min()
    date_max = df["review_date"].max()

    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        f.write("# Google Play ChatGPT 10k Review Collection Summary\n\n")

        f.write("## Collection Setup\n\n")
        f.write(f"- Source: Google Play Store\n")
        f.write(f"- App: {APP_NAME}\n")
        f.write(f"- App ID: `{APP_ID}`\n")
        f.write(f"- Country: `{COUNTRY}`\n")
        f.write(f"- Language: `{LANGUAGE}`\n")
        f.write(f"- Reviews requested: {NUM_REVIEWS}\n")
        f.write(f"- Reviews collected: {len(df)}\n")
        f.write(f"- Runtime: {runtime_seconds:.2f} seconds\n")
        f.write(f"- Output file: `{OUTPUT_PATH}`\n\n")

        f.write("## Date Range\n\n")
        f.write(f"- Earliest review date in sample: {date_min}\n")
        f.write(f"- Latest review date in sample: {date_max}\n\n")

        f.write("## Rating Distribution\n\n")
        f.write(rating_distribution.to_markdown())
        f.write("\n\n")

        f.write("## Missing Field Summary\n\n")
        f.write(missing_df.to_markdown())
        f.write("\n\n")

        f.write("## Review Length Summary\n\n")
        f.write(review_length_summary.to_markdown())
        f.write("\n\n")

        f.write("## Duplicate / Low-Signal Checks\n\n")
        f.write(f"- Duplicate review text count: {duplicate_count}\n")
        f.write(f"- Low-signal review count: {low_signal_count} ({low_signal_percent}%)\n\n")

        f.write("## Top App Versions\n\n")
        f.write(app_version_top.to_markdown())
        f.write("\n\n")

        f.write("## Initial Notes\n\n")
        f.write(
            "- This is a first-pass exploratory analysis of Google Play reviews for ChatGPT.\n"
            "- The dataset should be further checked for multilingual content, repeated text, "
            "very short reviews, emoji-heavy reviews, and other user-generated-content noise.\n"
            "- This collection uses a third-party scraper package for prototype testing. "
            "Long-term production use would require further review of official API access, "
            "permissions, and policy constraints.\n"
        )


# Main collection logic
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

    print("Starting Google Play ChatGPT review collection...")
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

    if df.empty:
        df.to_csv(OUTPUT_PATH, index=False)
        print("\nNo reviews were collected.")
        print(f"Saved empty file to: {OUTPUT_PATH}")
        return

    # Add basic EDA features
    df = add_review_length_features(df)
    df = identify_low_signal_reviews(df)

    # Duplicate check based on review text
    duplicate_count = int(df.duplicated(subset=["review_text_clean"]).sum())

    # Save full dataset
    df.to_csv(OUTPUT_PATH, index=False)

    end_time = time.time()
    runtime_seconds = end_time - start_time

    print()
    print(f"Requested reviews: {NUM_REVIEWS}")
    print(f"Collected reviews: {len(df)}")
    print(f"Saved to: {OUTPUT_PATH}")
    print(f"Runtime: {runtime_seconds:.2f} seconds")

    # Missing fields
    missing_df = print_missing_summary(df)

    # Basic distributions
    print("\nRating distribution:")
    print(df["rating"].value_counts(dropna=False).sort_index().to_string())

    print("\nReview length summary:")
    print(df[["review_char_length", "review_word_count"]].describe().round(2).to_string())

    print("\nDuplicate / low-signal summary:")
    print(f"- Duplicate review text count: {duplicate_count}")
    print(f"- Low-signal review count: {int(df['is_low_signal'].sum())}")

    # Preview
    preview_cols = [
        "rating",
        "review_date",
        "app_version",
        "thumbs_up_count",
        "review_word_count",
        "is_low_signal",
        "review_text",
    ]

    print("\nPreview:")
    print(df[preview_cols].head(10).to_string(index=False))

    # Write markdown summary
    write_summary_markdown(
        df=df,
        missing_df=missing_df,
        runtime_seconds=runtime_seconds,
        duplicate_count=duplicate_count,
    )

    print(f"\nSummary written to: {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
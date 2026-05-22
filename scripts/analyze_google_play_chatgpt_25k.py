import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path


INPUT_PATH = Path("data/raw/google_play_chatgpt_25k.csv")
FIGURE_DIR = Path("outputs/figures")


def load_data() -> pd.DataFrame:
    """Load collected Google Play reviews."""
    df = pd.read_csv(INPUT_PATH)

    # Convert date columns if available
    df["review_date"] = pd.to_datetime(df["review_date"], errors="coerce")
    df["collected_at"] = pd.to_datetime(df["collected_at"], errors="coerce")

    # Make sure review text is string
    df["review_text_clean"] = df["review_text"].fillna("").astype(str).str.strip()

    # Add length features if not already present
    if "review_char_length" not in df.columns:
        df["review_char_length"] = df["review_text_clean"].str.len()

    if "review_word_count" not in df.columns:
        df["review_word_count"] = df["review_text_clean"].str.split().str.len()

    return df


def plot_rating_distribution(df: pd.DataFrame) -> None:
    """Plot count of reviews by rating."""
    rating_counts = df["rating"].value_counts().sort_index()

    plt.figure(figsize=(8, 5))
    rating_counts.plot(kind="bar")
    plt.title("Rating Distribution")
    plt.xlabel("Rating")
    plt.ylabel("Number of Reviews")
    plt.xticks(rotation=0)
    plt.tight_layout()

    output_path = FIGURE_DIR / "chatgpt_rating_distribution.png"
    plt.savefig(output_path, dpi=200)
    plt.close()

    print(f"Saved: {output_path}")


def plot_review_length_distribution(df: pd.DataFrame) -> None:
    """Plot distribution of review word counts."""
    # Cap at 50 words to make the plot readable
    clipped_word_count = df["review_word_count"].clip(upper=50)

    plt.figure(figsize=(8, 5))
    plt.hist(clipped_word_count, bins=50)
    plt.title("Review Word Count Distribution")
    plt.xlabel("Review Word Count (clipped at 50)")
    plt.ylabel("Number of Reviews")
    plt.tight_layout()

    output_path = FIGURE_DIR / "chatgpt_review_length_distribution.png"
    plt.savefig(output_path, dpi=200)
    plt.close()

    print(f"Saved: {output_path}")


def plot_reviews_over_time(df: pd.DataFrame) -> None:
    """Plot number of reviews per day."""
    daily_counts = (
        df.dropna(subset=["review_date"])
        .set_index("review_date")
        .resample("D")
        .size()
    )

    plt.figure(figsize=(10, 5))
    daily_counts.plot(kind="line")
    plt.title("Reviews Over Time")
    plt.xlabel("Review Date")
    plt.ylabel("Number of Reviews")
    plt.tight_layout()

    output_path = FIGURE_DIR / "chatgpt_reviews_over_time.png"
    plt.savefig(output_path, dpi=200)
    plt.close()

    print(f"Saved: {output_path}")


def plot_top_app_versions(df: pd.DataFrame) -> None:
    """Plot top app versions by review count."""
    version_counts = (
        df["app_version"]
        .fillna("Missing")
        .value_counts()
        .head(10)
        .sort_values()
    )

    plt.figure(figsize=(10, 6))
    version_counts.plot(kind="barh")
    plt.title("Top App Versions by Review Count")
    plt.xlabel("Number of Reviews")
    plt.ylabel("App Version")
    plt.tight_layout()

    output_path = FIGURE_DIR / "chatgpt_top_app_versions.png"
    plt.savefig(output_path, dpi=200)
    plt.close()

    print(f"Saved: {output_path}")


def main():
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    df = load_data()

    print(f"Loaded {len(df)} reviews from {INPUT_PATH}")

    plot_rating_distribution(df)
    plot_review_length_distribution(df)
    plot_reviews_over_time(df)
    plot_top_app_versions(df)

    print("EDA figures generated successfully.")


if __name__ == "__main__":
    main()

from pathlib import Path
import re
import pandas as pd
import matplotlib.pyplot as plt

# ==========================================================
# FILE PATHS
# ==========================================================

BASE = Path.home() / "Documents" / "Output"

INPUT_FILE = BASE / "articles_playwright_hybrid_dataset_cleaned.csv"
QUALITY_REPORT = BASE / "cleaning_quality_report.csv"

DASHBOARD_FOLDER = Path.home() / "Desktop" / "News_Dashboard"
CHARTS_FOLDER = DASHBOARD_FOLDER / "charts"

CHARTS_FOLDER.mkdir(parents=True, exist_ok=True)

# ==========================================================
# HELPERS
# ==========================================================

def find_column(columns, candidates):
    mapping = {str(c).strip().lower(): c for c in columns}

    for candidate in candidates:
        if candidate in mapping:
            return mapping[candidate]

    return None


def clean_label(value):
    if pd.isna(value):
        return "Unknown"

    value = str(value).strip()

    if not value:
        return "Unknown"

    return value


def infer_category(row, title_col, text_col, description_col):
    """Estimate a broad topic when no category column exists."""
    parts = []

    for col in (title_col, description_col, text_col):
        if col:
            value = row.get(col, "")
            if pd.notna(value):
                parts.append(str(value)[:3000])

    content = " ".join(parts).lower()

    rules = {
        "AI & Technology": [
            "artificial intelligence", "machine learning",
            "technology", "robotics", "software", "cybersecurity",
            "artificial intelligence", "chatgpt", "data science"
        ],
        "Business & Finance": [
            "business", "economy", "economic", "stock market",
            "finance", "bank", "inflation", "company", "market"
        ],
        "Politics": [
            "politics", "political", "election", "president",
            "prime minister", "parliament", "government",
            "senate", "minister"
        ],
        "Health": [
            "health", "medical", "hospital", "disease",
            "doctor", "medicine", "patient", "vaccine"
        ],
        "Science & Space": [
            "science", "scientist", "research", "space",
            "nasa", "planet", "astronomy", "discovery"
        ],
        "Sports": [
            "sports", "football", "cricket", "tennis",
            "basketball", "match", "tournament", "player"
        ],
        "Environment": [
            "climate", "environment", "pollution", "wildlife",
            "renewable energy", "global warming", "emissions"
        ],
        "World News": [
            "international", "war", "conflict", "foreign",
            "diplomatic", "border", "united nations"
        ]
    }

    for category, keywords in rules.items():
        if any(keyword in content for keyword in keywords):
            return category

    return "Other / Unclassified"


def save_chart(filename):
    path = CHARTS_FOLDER / filename
    plt.tight_layout()
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


# ==========================================================
# MAIN
# ==========================================================

def main():
    if not INPUT_FILE.exists():
        print("ERROR: Cleaned CSV was not found:")
        print(INPUT_FILE)
        print("\nCheck that your cleaned CSV is in Documents\\Output.")
        return

    print("Loading cleaned dataset...")

    # Read in chunks is useful for large files, but charts need
    # grouped data. This dataset is expected to have about 100k rows.
    df = pd.read_csv(
        INPUT_FILE,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
        on_bad_lines="error"
    )

    if df.empty:
        print("ERROR: The cleaned CSV has no data rows.")
        return

    df.columns = [str(c).strip() for c in df.columns]

    print(f"Rows loaded: {len(df):,}")
    print(f"Columns found: {len(df.columns)}")

    # Detect useful columns.
    source_col = find_column(
        df.columns,
        ["source", "source_name", "publisher", "news_source", "website"]
    )
    date_col = find_column(
        df.columns,
        ["published_at", "published", "publication_date",
         "published_date", "date", "pub_date"]
    )
    title_col = find_column(
        df.columns, ["title", "headline", "article_title"]
    )
    text_col = find_column(
        df.columns,
        ["text", "article_text", "full_text", "content", "body", "article"]
    )
    description_col = find_column(
        df.columns, ["description", "summary", "excerpt", "snippet"]
    )
    category_col = find_column(
        df.columns,
        ["category", "news_category", "topic", "section", "genre"]
    )

    print("Source column:", source_col)
    print("Date column:", date_col)
    print("Category column:", category_col)

    # ------------------------------------------------------
    # CHART 1: TOP 10 NEWS SOURCES
    # ------------------------------------------------------

    print("\nCreating chart 1: Top 10 sources...")

    plt.figure(figsize=(11, 6))

    if source_col:
        sources = df[source_col].map(clean_label)
        top_sources = sources.value_counts().head(10).sort_values()

        top_sources.plot(kind="barh")
        plt.title("Top 10 News Sources by Article Count")
        plt.xlabel("Number of Articles")
        plt.ylabel("News Source")
    else:
        plt.text(
            0.5, 0.5,
            "No source/publisher column was found.",
            ha="center", va="center
"
        )
        plt.axis("off")

    save_chart("01_top_10_news_sources.png")

    # ------------------------------------------------------
    # CHART 2: ARTICLES OVER TIME
    # ------------------------------------------------------

    print("Creating chart 2: Articles over time...")

    plt.figure(figsize=(12, 6))

    if date_col:
        raw_dates = df[date_col].astype(str).str.strip()

        parsed_dates = pd.to_datetime(
            raw_dates.replace("", pd.NA),
            errors="coerce",
            utc=True,
            format="mixed"
        )

        valid_dates = parsed_dates.dropna()

        if not valid_dates.empty:
            monthly_counts = (
                valid_dates.dt.tz_convert(None)
                .dt.to_period("M")
                .value_counts()
                .sort_index()
            )

            monthly_counts.index = monthly_counts.index.astype(str)
            monthly_counts.plot(kind="line", marker="o")

            plt.title("News Articles Over Time (Monthly)")
            plt.xlabel("Publication Month")
            plt.ylabel("Number of Articles")
            plt.xticks(rotation=45, ha="right")
            plt.grid(True, alpha=0.3)
        else:
            plt.text(
                0.5, 0.5,
                "No valid publication dates were found.",
                ha="center", va="center"
            )
            plt.axis("off")
    else:
        plt.text(
            0.5, 0.5,
            "No publication-date column was found.",
            ha="center", va="center"
        )
        plt.axis("off")

    save_chart("02_articles_over_time.png")

    # ------------------------------------------------------
    # CHART 3: NEWS CATEGORIES
    # ------------------------------------------------------

    print("Creating chart 3: News categories...")

    plt.figure(figsize=(10, 7))

    if category_col:
        categories = df[category_col].map(clean_label)
        categories = categories.replace("", "Unknown")
    else:
        print(
            "No category column found; estimating categories "
            "from article text."
        )
        categories = df.apply(
            lambda row: infer_category(
                row, title_col, text_col, description_col
            ),
            axis=1
        )

    category_counts = categories.value_counts().head(12).sort_values()

    category_counts.plot(kind="barh")
    plt.title("News Articles by Category")
    plt.xlabel("Number of Articles")
    plt.ylabel("Category")

    if not category_col:
        plt.figtext(
            0.01, 0.01,
            "Estimated from keywords; categories may be imperfect.",
            fontsize=8
        )

    save_chart("03_news_categories.png")

    # ------------------------------------------------------
    # CHART 4: DATA CLEANING REPORT
    # ------------------------------------------------------

    print("Creating chart 4: Data cleaning report...")

    plt.figure(figsize=(12, 7))

    if QUALITY_REPORT.exists():
        report = pd.read_csv(
            QUALITY_REPORT,
            encoding="utf-8-sig"
        )

        if (
            "column" in report.columns
            and "missing_cells_after" in report.columns
        ):
            report["missing_cells_after"] = pd.to_numeric(
                report["missing_cells_after"],
                errors="coerce"
            ).fillna(0)

            report = report.sort_values(
                "missing_cells_after", ascending=False
            )

            report = report[report["missing_cells_after"] > 0].head(15)

            if not report.empty:
                report = report.sort_values("missing_cells_after")
                plt.barh(
                    report["column"].astype(str),
                    report["missing_cells_after"]
                )
                plt.title("Missing Cells by Column After Cleaning")
                plt.xlabel("Number of Missing Cells")
                plt.ylabel("Column")
            else:
                plt.text(
                    0.5, 0.5,
                    "The cleaning report shows no missing cells.",
                    ha="center", va="center"
                )
                plt.axis("off")
        else:
            plt.text(
                0.5, 0.5,
                "Cleaning report does not have the expected columns.",
                ha="center", va="center"
            )
            plt.axis("off")
    else:
        missing = df.replace(r"^\s*$", pd.NA, regex=True).isna().sum()
        missing = missing[missing > 0].sort_values().tail(15)

        if not missing.empty:
            missing.plot(kind="barh")
            plt.title("Missing Cells in the Cleaned Dataset")
            plt.xlabel("Number of Missing Cells")
            plt.ylabel("Column")
        else:
            plt.text(
                0.5, 0.5,
                "No empty cells were detected by this check.",
                ha="center", va="center"
            )
            plt.axis("off")

    save_chart("04_data_cleaning_report.png")

    # ------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------

    print("\n" + "=" * 55)
    print("ALL CHARTS COMPLETED")
    print("=" * 55)
    print(f"Rows visualized: {len(df):,}")
    print(f"Charts folder: {CHARTS_FOLDER}")
    print("\nFiles created:")
    print("01_top_10_news_sources.png")
    print("02_articles_over_time.png")
    print("03_news_categories.png")
    print("04_data_cleaning_report.png")
    print("\nNote: inferred categories are estimates, not verified labels.")


if __name__ == "__main__":
    main()

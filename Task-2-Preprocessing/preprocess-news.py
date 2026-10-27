
import pandas as pd
import re
import html
from pathlib import Path
from bs4 import BeautifulSoup

# Input and output files
BASE = Path.home() / "Documents" / "Output"

INPUT_FILE = BASE / "articles_playwright_hybrid_dataset.csv"
OUTPUT_FILE = BASE / "articles_playwright_hybrid_dataset_cleaned.csv"

BATCH_SIZE = 5000


def normalize_text(value):
    """Normalize article text without removing useful punctuation."""
    if pd.isna(value):
        return ""

    text = html.unescape(str(value))
    text = BeautifulSoup(text, "html.parser").get_text(" ")
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()

    return text


def find_column(columns, candidates):
    """Find a matching column name, ignoring case."""
    mapping = {str(c).strip().lower(): c for c in columns}

    for candidate in candidates:
        if candidate in mapping:
            return mapping[candidate]

    return None


def main():
    if not INPUT_FILE.exists():
        print(f"ERROR: Input file not found:\n{INPUT_FILE}")
        return

    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    # Read column names only
    columns = pd.read_csv(INPUT_FILE, nrows=0).columns.tolist()

    text_col = find_column(
        columns,
        ["article_text", "full_text", "content", "text", "body", "article"]
    )

    title_col = find_column(columns, ["title", "headline"])
    url_col = find_column(columns, ["url", "link", "article_url"])

    if not text_col and not title_col:
        print("ERROR: Could not identify a title or article-text column.")
        print("Available columns:", columns)
        return

    print("Input:", INPUT_FILE)
    print("Output:", OUTPUT_FILE)
    print("Text column:", text_col)
    print("Title column:", title_col)
    print("URL column:", url_col)
    print("\nStarting preprocessing...")

    total_read = 0
    total_written = 0
    total_duplicates = 0
    total_empty = 0
    seen_urls = set()
    seen_content = set()

    first_batch = True

    for chunk in pd.read_csv(
        INPUT_FILE,
        chunksize=BATCH_SIZE,
        dtype=str,
        keep_default_na=False,
        on_bad_lines="warn"
    ):
        total_read += len(chunk)

        # Normalize text fields
        for col in [text_col, title_col]:
            if col:
                chunk[col] = chunk[col].map(normalize_text)

        # Normalize URLs for duplicate checking
        if url_col:
            chunk["_url_key"] = (
                chunk[url_col]
                .astype(str)
                .str.strip()
                .str.rstrip("/")
                .str.lower()
            )
        else:
            chunk["_url_key"] = ""

        # Remove empty records with no usable title or text
        usable = pd.Series(False, index=chunk.index)

        if title_col:
            usable |= chunk[title_col].str.len() > 0

        if text_col:
            usable |= chunk[text_col].str.len() > 0

        total_empty += int((~usable).sum())
        chunk = chunk.loc[usable].copy()

        keep_rows = []

        for idx, row in chunk.iterrows():
            url_key = row["_url_key"]
            content = row[text_col] if text_col else ""
            title = row[title_col] if title_col else ""

            # Prefer URL for identifying the same article.
            # If URL is absent, use normalized title + text.
            if url_key:
                key = ("url", url_key)
            else:
                key = ("content", title, content)

            if key in seen_content:
                total_duplicates += 1
                continue

            seen_content.add(key)
            keep_rows.append(idx)

            if url_key:
                seen_urls.add(url_key)

        chunk = chunk.loc[keep_rows].drop(columns=["_url_key"])

        # Append each cleaned batch to the output CSV
        if not chunk.empty:
            chunk.to_csv(
                OUTPUT_FILE,
                index=False,
                mode="w" if first_batch else "a",
                header=first_batch,
                encoding="utf-8-sig"
            )
            first_batch = False
            total_written += len(chunk)

        print(
            f"Processed: {total_read:,} | "
            f"Cleaned so far: {total_written:,} | "
            f"Duplicates: {total_duplicates:,}"
        )

    if first_batch:
        print("No usable articles found. Output CSV was not created.")
        return

    print("\nPREPROCESSING COMPLETE")
    print("Rows read:", f"{total_read:,}")
    print("Rows exported:", f"{total_written:,}")
    print("Duplicates removed:", f"{total_duplicates:,}")
    print("Empty rows removed:", f"{total_empty:,}")
    print("Cleaned CSV:", OUTPUT_FILE)


if __name__ == "__main__":
    main()

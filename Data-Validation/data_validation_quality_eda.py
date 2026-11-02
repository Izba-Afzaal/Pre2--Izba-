import json
import re
import warnings
from pathlib import Path
from urllib.parse import urlparse
import urllib.parse
import base64

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

# -------------------------------------------------------------------------
# INPUT / OUTPUT paths
# -------------------------------------------------------------------------
DATA_INPUT_PATH = Path("C:/Users/admin/Documents/validation output/news_validated_final.csv")
OUTPUT_DIR = Path("C:/Users/admin/Documents/eda_output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"Loading data from: {DATA_INPUT_PATH.resolve()}...")
df = pd.read_csv(DATA_INPUT_PATH, low_memory=False)
print(f"Loaded shape: {df.shape}")

# -------------------------------------------------------------------------
# 1. DOMAIN EXTRACTION (robust handling of Google News URLs)
# -------------------------------------------------------------------------
def extract_url_domain(u, src=None):
    """
    Robustly extract the true publisher domain from a URL.
    Handles:
    * Direct article URLs (e.g., https://nytimes.com/...),
    * Google News RSS URLs that embed a percent‑encoded original URL,
    * Google News URLs with a base64‑encoded token after '/articles/'.
    The optional `src` argument is kept for signature compatibility.
    """
    if not isinstance(u, str) or not u.strip():
        return ""
    try:
        # Simple hostname extraction
        p = urlparse(u.strip())
        h = (p.hostname or "").lower()
        if h.startswith("www."):
            h = h[4:]

        # Direct domain (non‑Google‑News) – we’re done
        if h and h != "news.google.com":
            return h

        # -------------------------------------------------------------
        # Google News aggregator handling
        # -------------------------------------------------------------
        # 1. Repeated percent‑decode to expose any embedded URL
        decoded = u
        for _ in range(5):
            nd = urllib.parse.unquote(decoded)
            if nd == decoded:
                break
            decoded = nd

        # Look for a full URL inside the decoded string
        match = re.search(r"https?://([^/]+)/", decoded)
        if match:
            dom = match.group(1).lower()
            if dom.startswith("www."):
                dom = dom[4:]
            return dom

        # 2. Try to decode a base64 token after '/articles/'
        b64_match = re.search(r"/articles/([^/]+)", u)
        if b64_match:
            token = b64_match.group(1)
            # Pad the token for proper base64 decoding
            padding = "=" * (-len(token) % 4)
            try:
                decoded_bytes = base64.urlsafe_b64decode(token + padding)
                decoded_str = decoded_bytes.decode(errors="ignore")
                url_match = re.search(r"https?://([^/]+)/", decoded_str)
                if url_match:
                    dom = url_match.group(1).lower()
                    if dom.startswith("www."):
                        dom = dom[4:]
                    return dom
            except Exception:
                pass

        # Fallback – return the original hostname (likely news.google.com)
        return h
    except Exception:
        return ""

print("Extracting domain strictly from the 'url' column...")
df["domain"] = df["url"].apply(lambda u: extract_url_domain(u))

# -------------------------------------------------------------------------
# 2. MAP GENERIC PLACEHOLDER DOMAINS USING THE SOURCE COLUMN
# -------------------------------------------------------------------------
GENERIC_DOMAINS = {
    "news.google.com", "politics.com", "business.com", "technology.com",
    "worldnews.com", "economy.com", "education.com", "health.com",
    "cybersecurity.com", "science.com"
}

def map_domain_from_source(domain, source):
    """Replace generic placeholder domains with real ones derived from the source field."""
    if domain not in GENERIC_DOMAINS:
        return domain
    if not isinstance(source, str):
        return domain

    # Extract publisher name between pipes: "Publisher history | PublisherName | ..."
    pub_match = re.search(r"\|\s*([^|]+?)\s*\|", source)
    if not pub_match:
        return domain
    publisher = pub_match.group(1).strip().lower()

    # Known publisher → domain map
    special = {
        "politico": "politico.com",
        "the guardian": "theguardian.com",
        "guardian": "theguardian.com",
        "bbc": "bbc.co.uk",
        "reuters": "reuters.com",
        "cnn": "cnn.com",
        "axios": "axios.com",
        "nytimes": "nytimes.com",
        "washington post": "washingtonpost.com",
        "wall street journal": "wsj.com",
    }
    for key, dom in special.items():
        if key in publisher:
            return dom

    # Generic fallback – strip non‑alphanumerics, collapse spaces, add .com
    gen = re.sub(r"[^a-z0-9]", "", publisher.replace(" ", ""))
    if gen:
        return f"{gen}.com"
    return domain

# Apply the mapping across the DataFrame
df["domain"] = df.apply(lambda row: map_domain_from_source(row["domain"], row.get("source")), axis=1)

print(f"Unique domains: {df['domain'].nunique()}")
print("Top domains:")
print(df["domain"].value_counts().head(10))

# -------------------------------------------------------------------------
# 3. CATEGORY CLASSIFICATION (technology, stock, energy, politics, health)
# -------------------------------------------------------------------------
CATEGORY_KEYWORDS = {
    "technology": [
        r"\b(?:ai|artificial intelligence|tech|technology|software|hardware|app|apps|chip|chips|semiconductor|computing|cyber|cybersecurity|cloud|google|apple|microsoft|nvidia|meta|amazon|openai|chatgpt|robot|robotics|algorithm|data|quantum|gadget|gadgets|smartphone|iphone|android|crypto|bitcoin|blockchain|internet|social media|hacker|malware)\b"
    ],
    "stock": [
        r"\b(?:stock|stocks|shares|market|markets|nasdaq|dow|s\&p|wall street|investor|investors|investment|trading|trader|traders|equity|equities|earnings|revenue|profit|loss|dividend|ipo|valuation|bond|bonds|treasury|yield|interest rate|inflation|recession|federal reserve|fed|central bank|banking|bank|fintech|gdp|economy|economic|quarterly)\b"
    ],
    "energy": [
        r"\b(?:energy|oil|crude|petroleum|gas|natural gas|diesel|fuel|opec|refinery|pipeline|renewable|solar|wind|nuclear|electricity|power grid|carbon|emission|emissions|clean energy|coal|drilling|battery|ev|electric vehicle|climate|greenhouse|climate change|fossil)\b"
    ],
    "politics": [
        r"\b(?:politics|political|election|elections|vote|voters|voting|ballot|president|presidential|trump|biden|harris|democrat|democrats|republican|republicans|gop|congress|senate|senator|senators|parliament|governor|government|white house|capitol|supreme court|court|judge|lawmaker|lawmakers|legislation|bill|policy|diplomacy|diplomat|treaty|foreign policy|minister|prime minister|party|campaign|poll|polls|cabinet)\b"
    ],
    "health": [
        r"\b(?:health|healthcare|medical|medicine|hospital|hospitals|doctor|doctors|physician|patient|patients|nurse|disease|diseases|cancer|virus|viral|flu|covid|pandemic|vaccine|vaccines|vaccination|fda|cdc|who|mental health|drug|drugs|pharmaceutical|pharma|therapy|treatment|clinical|surgery|nutrition|diet|obesity|fitness|infection|diagnosis)\b"
    ]
}

COMPILED_PATTERNS = {cat: [re.compile(p, re.I) for p in pats] for cat, pats in CATEGORY_KEYWORDS.items()}
TOPIC_MAP = {
    "technology": "technology",
    "cybersecurity": "technology",
    "health": "health",
    "politics": "politics",
    "business": "stock",
    "economy": "stock",
    "climate": "energy",
}

def classify_category(row):
    src = str(row["source"]) if pd.notna(row["source"]) else ""
    # Try to infer from the source “Topic history” field
    m = re.search(r"Topic history\s*\|\s*([^|]+?)\s*\|", src)
    if m:
        topic = m.group(1).strip().lower()
        if topic in TOPIC_MAP:
            return TOPIC_MAP[topic]

    title = str(row["title"]) if pd.notna(row["title"]) else ""
    desc = str(row["description"]) if pd.notna(row["description"]) else ""

    scores = {cat: 0 for cat in CATEGORY_KEYWORDS}
    for cat, pats in COMPILED_PATTERNS.items():
        for pat in pats:
            scores[cat] += len(pat.findall(title)) * 3 + len(pat.findall(desc))

    # Boost based on known source keywords
    src_lower = src.lower()
    if "politico" in src_lower or "politics" in src_lower:
        scores["politics"] += 2
    if "tech" in src_lower or "register" in src_lower or "wired" in src_lower:
        scores["technology"] += 2
    if "health" in src_lower or "medical" in src_lower:
        scores["health"] += 2
    if "cnbc" in src_lower or "market" in src_lower or "bloomberg" in src_lower or "economy" in src_lower:
        scores["stock"] += 2
    if "energy" in src_lower or "oil" in src_lower:
        scores["energy"] += 2

    best_cat = max(scores, key=scores.get)
    if scores[best_cat] > 0:
        return best_cat

    # Fallback heuristics
    if "science" in src_lower or "education" in src_lower:
        return "technology"
    return "politics"

print("Classifying articles into categories: technology, stock, energy, politics, health...")
df["category"] = df.apply(classify_category, axis=1)

# -------------------------------------------------------------------------
# 4. SAVE UPDATED DATASET
# -------------------------------------------------------------------------
# Preserve original column order + the new columns
core_cols = ['article_id', 'source', 'title', 'description', 'author',
             'url', 'published_at', 'timezone', 'scraped_at',
             'domain', 'category']
extra_cols = [c for c in df.columns if c not in core_cols]
df_save = df[core_cols + extra_cols]

# Write to a new, writable file (original file is read‑only)
df_save.to_csv(Path("C:/Users/admin/Documents/validation output/news_validated_final_corrected.csv"),
               index=False, encoding="utf-8-sig")
print("Saved updated datasets successfully!")

# -------------------------------------------------------------------------
# 5. RE‑GENERATE ALL EDA OUTPUTS & CHARTS
# -------------------------------------------------------------------------
COLS = {
    "url": "url",
    "title": "title",
    "content": "description",
    "published": "published_at",
    "scraped": "scraped_at",
    "author": "author",
    "domain": "domain",
    "category": "category",
}

# --- Section 4: Dataset Overview & Schema ---
overview = pd.DataFrame({
    "dtype": df.dtypes.astype(str),
    "non_null": df.notna().sum(),
    "missing": df.isna().sum(),
    "missing_pct": (df.isna().mean() * 100).round(2),
    "unique_non_null": df.nunique(dropna=True),
})
overview.to_csv(OUTPUT_DIR / "column_profile.csv")

exact_dupes = int(df.duplicated().sum())

# --- Section 5: Missingness & Completeness ---
missing_summary = overview[["missing", "missing_pct"]].sort_values("missing_pct", ascending=False)
missing_summary.to_csv(OUTPUT_DIR / "missingness_summary.csv")

plt.figure(figsize=(10, 4.5))
ax = missing_summary["missing_pct"].plot(kind="bar", color="#2b5c8f")
ax.set_title("Missing values by column (%)", fontsize=14, fontweight="bold")
ax.set_ylabel("Missing (%)", fontsize=11)
ax.set_xlabel("Column", fontsize=11)
ax.set_ylim(0, 100)
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "missing_values_by_column.png", dpi=150)
plt.close()

# Grouped missingness by domain
tmp = df.copy()
tmp["_domain_for_group"] = tmp["domain"].fillna("(missing domain)")
dom_missing_records = []
for dom, group in tmp.groupby("_domain_for_group", dropna=False):
    row_m = {"domain": dom, "articles": len(group)}
    row_m["author_missing_pct"] = group["author"].isna().mean() * 100
    row_m["published_missing_pct"] = group["published_at"].isna().mean() * 100
    dom_missing_records.append(row_m)
dom_missing_df = pd.DataFrame(dom_missing_records).sort_values("articles", ascending=False).round(2)
dom_missing_df.to_csv(OUTPUT_DIR / "missingness_by_domain.csv", index=False)

# --- Section 6: Duplicate Patterns ---
duplicate_stats = {
    "exact_duplicate_rows": exact_dupes,
    "duplicate_url_rows": int(df["url"].duplicated(keep=False).sum()),
    "duplicate_title_rows": int(df["title"].astype("string").str.strip().duplicated(keep=False).sum()),
    "duplicate_content_rows": int(df["description"].astype("string").str.strip().duplicated(keep=False).sum()),
}
pd.Series(duplicate_stats, name="row_count").to_csv(OUTPUT_DIR / "duplicate_summary.csv")

# --- Section 7: Text‑Length Distributions ---
df["_title_chars"] = df["title"].astype("string").str.len()
df["_title_words"] = df["title"].astype("string").str.split().str.len()
df["_content_chars"] = df["description"].astype("string").str.len()
df["_content_words"] = df["description"].astype("string").str.split().str.len()

length_cols = ["_title_chars", "_title_words", "_content_chars", "_content_words"]
length_stats = df[length_cols].describe(percentiles=[.01, .05, .25, .5, .75, .95, .99]).T
length_stats.to_csv(OUTPUT_DIR / "text_length_quantiles.csv")

for col, color in zip(length_cols,
                      ["#2b5c8f", "#3690c0", "#e6550d", "#fd8d3c"]):
    values = pd.to_numeric(df[col], errors="coerce").dropna()
    plt.figure(figsize=(8, 4))
    plt.hist(values, bins=50, color=color, edgecolor="black")
    plt.title(f"Distribution of {col[1:]}", fontsize=13)
    plt.xlabel("Count", fontsize=11)
    plt.ylabel("Frequency", fontsize=11)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"dist__{col[1:]}.png", dpi=150)
    plt.close()

# --- Section 8: Domain‑Category Crosstab & Visualisations ---
domain_category_ct = pd.crosstab(df["domain"], df["category"])
domain_category_ct.to_csv(OUTPUT_DIR / "domain_category_crosstab.csv")

plt.figure(figsize=(12, 6))
domain_category_ct.plot(kind="bar", stacked=True, colormap="tab20")
plt.title("Category Composition per Domain", fontsize=14, fontweight="bold")
plt.xlabel("Domain", fontsize=12)
plt.ylabel("Article Count", fontsize=12)
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "category_composition_by_domain.png", dpi=150)
plt.close()

# --- Section 9: Overall Category Distribution ---
cat_counts = df["category"].value_counts()
cat_counts.to_csv(OUTPUT_DIR / "category_distribution.csv")
plt.figure(figsize=(8, 5))
cat_counts.plot(kind="pie", autopct="%1.1f%%", startangle=140, colors=plt.cm.Set3.colors)
plt.title("Overall Category Distribution", fontsize=14)
plt.ylabel("")
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "category_distribution.png", dpi=150)
plt.close()

# --- Section 10: Temporal Patterns (optional) ---
df["published_at_dt"] = pd.to_datetime(df["published_at"], errors="coerce")
if not df["published_at_dt"].isna().all():
    articles_per_day = df.groupby(df["published_at_dt"].dt.date).size()
    articles_per_day.to_csv(OUTPUT_DIR / "articles_per_day.csv")
    plt.figure(figsize=(10, 4))
    articles_per_day.plot()
    plt.title("Articles per Day", fontsize=14)
    plt.xlabel("Date")
    plt.ylabel("Count")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "articles_per_day.png", dpi=150)
    plt.close()

    articles_by_weekday = df["published_at_dt"].dt.weekday.value_counts().sort_index()
    articles_by_weekday.to_csv(OUTPUT_DIR / "articles_by_weekday.csv")
    plt.figure(figsize=(8, 4))
    articles_by_weekday.plot(kind="bar", color="#2b5c8f")
    plt.title("Articles by Weekday", fontsize=14)
    plt.xlabel("Weekday (0=Mon)")
    plt.ylabel("Count")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "articles_by_weekday.png", dpi=150)
    plt.close()

# -------------------------------------------------------------------------
# 6. SUMMARY JSON
# -------------------------------------------------------------------------
summary = {
    "total_rows": int(df.shape[0]),
    "unique_domains": int(df["domain"].nunique()),
    "category_breakdown": df["category"].value_counts().to_dict(),
    "outputs_dir": str(OUTPUT_DIR),
}
with open(OUTPUT_DIR / "eda_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

print("\n")
print("======================================================================")
print("EDA PIPELINE COMPLETE WITH EXACT URL DOMAINS!")
print(f"Total Rows Analyzed: {df.shape[0]:,}")
print(f"Total Unique URL Domains: {df['domain'].nunique():,}")
print("Category Breakdown:")
print(df["category"].value_counts())
print(f"Outputs written to: {OUTPUT_DIR}")
print("======================================================================")
print("\n")
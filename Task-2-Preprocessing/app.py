
from pathlib import Path
import re
import pandas as pd
import streamlit as st
import plotly.express as px

# -------------------- CONFIGURATION --------------------

st.set_page_config(
    page_title="News Intelligence | Analytics",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path.home() / "Desktop" / "News_Dashboard"
DATA_DIR = Path.home() / "Documents" / "Output"

# -------------------- STYLING --------------------

st.markdown("""
<style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1600px;
    }
    [data-testid="stSidebar"] {
        border-right: 1px solid rgba(128,128,128,0.2);
    }
    div[data-testid="stMetric"] {
        background: var(--secondary-background-color);
        border: 1px solid rgba(128,128,128,0.2);
        padding: 16px;
        border-radius: 12px;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.9rem;
    }
    .hero {
        padding: 22px 24px;
        border-radius: 16px;
        background: linear-gradient(120deg, #132743, #24527a);
        color: white;
        margin-bottom: 20px;
    }
    .hero h1 {
        color: white;
        margin: 0;
        font-size: 2rem;
    }
    .hero p {
        color: #e0eaf5;
        margin: 8px 0 0 0;
    }
    .small-note {
        color: var(--text-color);
        opacity: 0.7;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)


# -------------------- DATA DISCOVERY --------------------

def discover_csv_files():
    """Find likely news datasets in common project locations."""
    folders = [
        DATA_DIR,
        BASE_DIR,
        BASE_DIR / "data",
    ]

    found = {}

    for folder in folders:
        if not folder.exists():
            continue

        for path in folder.glob("*.csv"):
            name = path.name.lower()

            # Exclude audit/report files from the dataset picker.
            if any(word in name for word in [
                "quality_report",
                "removed_duplicates",
                "rejected_records",
            ]):
                continue

            found[str(path)] = path

    return list(found.values())


def read_csv_safely(path):
    """Read a CSV with common encoding fallbacks."""
    last_error = None

    for encoding in ["utf-8", "utf-8-sig", "cp1252", "latin1"]:
        try:
            return pd.read_csv(
                path,
                encoding=encoding,
                low_memory=False,
                on_bad_lines="skip",
            )
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc

    raise ValueError(f"Could not read this CSV: {last_error}")


@st.cache_data(show_spinner="Loading news dataset...")
def load_dataset(path_string, file_size, modified_time):
    # Size and modification time help refresh the cache after a file changes.
    del file_size, modified_time
    return read_csv_safely(Path(path_string))


def find_column(df, candidates):
    """Find a column by checking common names."""
    lookup = {
        re.sub(r"[^a-z0-9]", "", str(col).lower()): col
        for col in df.columns
    }

    for candidate in candidates:
        key = re.sub(r"[^a-z0-9]", "", candidate.lower())
        if key in lookup:
            return lookup[key]

    return None


def safe_text(series):
    return series.fillna("").astype(str).str.strip()


def make_category(text):
    """Estimate a category when the dataset has no category column."""
    text = str(text).lower()

    groups = {
        "Artificial Intelligence": [
            "artificial intelligence", "machine learning",
            "deep learning", "generative ai", "chatgpt", "llm",
            "neural network",
        ],
        "Technology": [
            "technology", "software", "cybersecurity", "computer",
            "smartphone", "internet", "startup", "tech company",
        ],
        "Business & Economy": [
            "economy", "economic", "inflation", "market", "stock",
            "business", "trade", "bank", "company", "finance",
        ],
        "Politics": [
            "politics", "political", "government", "minister",
            "election", "parliament", "president", "senate",
        ],
        "Science & Space": [
            "science", "scientist", "space", "nasa", "planet",
            "research study", "astronomy", "physics",
        ],
        "Health": [
            "health", "medical", "hospital", "disease",
            "doctor", "medicine", "public health",
        ],
        "Sports": [
            "sports", "football", "cricket", "tennis",
            "basketball", "olympics", "championship",
        ],
        "Environment": [
            "climate", "environment", "global warming",
            "wildlife", "pollution", "renewable energy",
        ],
    }

    for category, keywords in groups.items():
        if any(keyword in text for keyword in keywords):
            return category

    return "Other / Unclassified"


# -------------------- SIDEBAR --------------------

st.sidebar.markdown("## 📰 News Intelligence")
st.sidebar.caption("News data • Research • Analytics")
st.sidebar.divider()

available_files = discover_csv_files()

uploaded_file = st.sidebar.file_uploader(
    "Upload a news CSV",
    type=["csv"],
    help="Optional: upload a CSV if your dataset is not listed below.",
)

selected_path = None
df = None

if uploaded_file is not None:
    try:
        df = read_csv_safely(uploaded_file)
        st.sidebar.success("Uploaded dataset loaded")
    except Exception as exc:
        st.error(f"Could not load the uploaded CSV: {exc}")
        st.stop()

elif available_files:
    preferred = next(
        (
            path for path in available_files
            if "cleaned" in path.name.lower()
            and "news" in path.name.lower()
        ),
        None,
    )

    if preferred is None:
        preferred = next(
            (
                path for path in available_files
                if "news" in path.name.lower()
                and "dataset" in path.name.lower()
            ),
            available_files[0],
        )

    options = [str(path) for path in available_files]
    default_index = options.index(str(preferred))

    selected_path = st.sidebar.selectbox(
        "Choose dataset",
        options=options,
        index=default_index,
        format_func=lambda value: Path(value).name,
    )

    try:
        selected_file = Path(selected_path)
        df = load_dataset(
            selected_path,
            selected_file.stat().st_size,
            selected_file.stat().st_mtime,
        )
    except Exception as exc:
        st.error(f"Could not load the selected CSV: {exc}")
        st.stop()

else:
    st.markdown("## Dataset required")
    st.warning(
        "No CSV was found in Documents/Output or the dashboard folder. "
        "Upload your news CSV using the sidebar."
    )
    st.stop()

if df is None or df.empty:
    st.error("The selected CSV contains no readable data rows.")
    st.stop()

# Normalize column labels without changing their actual names.
df.columns = [str(col).strip() for col in df.columns]
df = df.loc[:, ~pd.Index(df.columns).duplicated()]

if len(df.columns) == 0:
    st.error("No usable columns were found in this CSV.")
    st.stop()

# -------------------- DETECT COLUMNS --------------------

source_col = find_column(df, [
    "source", "source_name", "publisher", "news_source", "publication"
])

title_col = find_column(df, [
    "title", "headline", "article_title", "news_title"
])

date_col = find_column(df, [
    "published_at", "publication_date", "published_date",
    "date", "publish_date", "datetime", "published"
])

url_col = find_column(df, [
    "url", "article_url", "link", "web_url"
])

author_col = find_column(df, [
    "author", "authors", "writer", "byline"
])

text_col = find_column(df, [
    "text", "article_text", "full_text", "content", "body"
])

description_col = find_column(df, [
    "description", "summary", "snippet", "abstract"
])

category_col = find_column(df, [
    "category", "news_category", "topic", "section"
])

# Build reliable display columns, even if some fields are missing.
if source_col:
    df["_source"] = safe_text(df[source_col]).replace("", "Unknown source")
else:
    df["_source"] = "Unknown source"

if title_col:
    df["_title"] = safe_text(df[title_col])
else:
    df["_title"] = ""

if text_col:
    df["_text"] = safe_text(df[text_col])
else:
    df["_text"] = ""

if description_col:
    df["_description"] = safe_text(df[description_col])
else:
    df["_description"] = ""

if url_col:
    df["_url"] = safe_text(df[url_col])
else:
    df["_url"] = ""

if author_col:
    df["_author"] = safe_text(df[author_col])
else:
    df["_author"] = ""

if date_col:
    df["_date"] = pd.to_datetime(
        df[date_col], errors="coerce", utc=True
    )
else:
    df["_date"] = pd.Series(
        pd.NaT, index=df.index, dtype="datetime64[ns, UTC]"
    )

if category_col:
    df["_category"] = (
        safe_text(df[category_col])
        .replace("", "Unknown / Unclassified")
    )
    category_note = f"Using existing column: {category_col}"
else:
    category_source = (
        df["_title"] + " " + df["_description"] + " " + df["_text"]
    )
    df["_category"] = category_source.map(make_category)
    category_note = (
        "Estimated from article keywords; these are not verified labels."
    )

# -------------------- HEADER --------------------

st.markdown("""
<div class="hero">
    <h1>News Intelligence Dashboard</h1>
    <p>Explore news coverage, publication patterns, sources and data quality.</p>
</div>
""", unsafe_allow_html=True)

st.caption(
    f"Dataset: {Path(selected_path).name if selected_path else uploaded_file.name}"
    if selected_path or uploaded_file
    else "News dataset"
)

# -------------------- NAVIGATION --------------------

page = st.sidebar.radio(
    "NAVIGATION",
    [
        "Overview",
        "News Analytics",
        "Article Explorer",
        "Data Quality",
    ],
)

st.sidebar.divider()
st.sidebar.caption(f"Rows loaded: {len(df):,}")
st.sidebar.caption(f"Columns: {len(df.columns):,}")

# -------------------- FILTERS --------------------

st.sidebar.markdown("### Filters")

source_options = sorted(df["_source"].dropna().unique().tolist())

selected_sources = st.sidebar.multiselect(
    "News sources",
    options=source_options,
    default=source_options,
)

valid_dates = df["_date"].dropna()
date_filter_enabled = False
start_date = None
end_date = None

if not valid_dates.empty:
    min_date = valid_dates.min().date()
    max_date = valid_dates.max().date()

    date_filter_enabled = st.sidebar.checkbox(
        "Filter by publication date",
        value=False,
    )

    if date_filter_enabled:
        date_range = st.sidebar.date_input(
            "Date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
            start_date, end_date = date_range
        elif isinstance(date_range, (tuple, list)) and len(date_range) == 1:
            start_date = end_date = date_range[0]

filtered = df[df["_source"].isin(selected_sources)].copy()

if date_filter_enabled and start_date and end_date:
    start_ts = pd.Timestamp(start_date, tz="UTC")
    end_ts = pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1)
    filtered = filtered[
        filtered["_date"].notna()
        & (filtered["_date"] >= start_ts)
        & (filtered["_date"] < end_ts)
    ]

st.sidebar.caption(f"Filtered rows: {len(filtered):,}")

if filtered.empty:
    st.warning("No articles match the selected filters. Change the filters in the sidebar.")
    st.stop()

# -------------------- KPI METRICS --------------------

def show_metrics(data):
    total = len(data)
    sources = data["_source"].nunique()
    dated = int(data["_date"].notna().sum())
    date_coverage = dated / total * 100 if total else 0

    if url_col:
        nonempty_urls = data["_url"].str.lower().replace("", pd.NA).dropna()
        unique_urls = nonempty_urls.nunique()
    else:
        unique_urls = None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Articles", f"{total:,}")
    c2.metric("Unique Sources", f"{sources:,}")
    c3.metric("Articles With Dates", f"{date_coverage:.1f}%")

    if unique_urls is not None:
        c4.metric("Unique URLs", f"{unique_urls:,}")
    else:
        c4.metric("Columns Available", f"{len(df.columns):,}")


# -------------------- OVERVIEW PAGE --------------------

if page == "Overview":
    show_metrics(filtered)

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("Top News Sources")
        source_counts = (
            filtered["_source"]
            .value_counts()
            .head(10)
            .rename_axis("Source")
            .reset_index(name="Articles")
        )
        fig = px.bar(
            source_counts.sort_values("Articles"),
            x="Articles",
            y="Source",
            orientation="h",
            text="Articles",
            template="plotly_white",
        )
        fig.update_layout(
            height=420,
            margin=dict(l=10, r=15, t=20, b=10),
            yaxis_title="",
        )
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Publication Timeline")
        dated = filtered.dropna(subset=["_date"]).copy()

        if not dated.empty:
            dated["_month"] = dated["_date"].dt.to_period("M").astype(str)
            timeline = (
                dated.groupby("_month")
                .size()
                .reset_index(name="Articles")
            )
            fig = px.line(
                timeline,
                x="_month",
                y="Articles",
                markers=True,
                template="plotly_white",
            )
            fig.update_layout(
                height=420,
                margin=dict(l=10, r=15, t=20, b=10),
                xaxis_title="Month",
                yaxis_title="Articles",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No valid publication dates are available for the timeline.")

    left, right = st.columns(2)

    with left:
        st.subheader("News Categories")
        category_counts = (
            filtered["_category"]
            .value_counts()
            .head(10)
            .rename_axis("Category")
            .reset_index(name="Articles")
        )
        fig = px.pie(
            category_counts,
            names="Category",
            values="Articles",
            hole=0.45,
            template="plotly_white",
        )
        fig.update_layout(height=390, margin=dict(l=5, r=5, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Dataset Snapshot")
        snapshot = pd.DataFrame({
            "Metric": [
                "Rows in dataset",
                "Columns in dataset",
                "Sources represented",
                "Rows with valid publication dates",
                "Rows with a title",
                "Rows with a URL",
            ],
            "Value": [
                f"{len(filtered):,}",
                f"{len(df.columns):,}",
                f"{filtered['_source'].nunique():,}",
                f"{filtered['_date'].notna().sum():,}",
                f"{(filtered['_title'] != '').sum():,}",
                f"{(filtered['_url'] != '').sum():,}",
            ],
        })
        st.dataframe(snapshot, hide_index=True, use_container_width=True)

# -------------------- NEWS ANALYTICS PAGE --------------------

elif page == "News Analytics":
    show_metrics(filtered)

    st.divider()
    st.subheader("Explore Source Performance")

    source_counts = (
        filtered["_source"]
        .value_counts()
        .rename_axis("Source")
        .reset_index(name="Articles")
    )

    if not source_counts.empty:
        fig = px.bar(
            source_counts.head(25),
            x="Source",
            y="Articles",
            color="Articles",
            template="plotly_white",
            title="Articles by Source (Top 25)",
        )
        fig.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Publication Activity")
    dated = filtered.dropna(subset=["_date"]).copy()

    if not dated.empty:
        frequency = st.selectbox(
            "Group publication dates by",
            ["Day", "Month", "Year"],
            index=1,
        )

        if frequency == "Day":
            dated["_period"] = dated["_date"].dt.strftime("%Y-%m-%d")
        elif frequency == "Year":
            dated["_period"] = dated["_date"].dt.strftime("%Y")
        else:
            dated["_period"] = dated["_date"].dt.strftime("%Y-%m")

        timeline = (
            dated.groupby("_period")
            .size()
            .reset_index(name="Articles")
        )

        fig = px.area(
            timeline,
            x="_period",
            y="Articles",
            template="plotly_white",
            title=f"Articles per {frequency.lower()}",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No valid dates were found.")

    st.subheader("Category Breakdown")
    st.caption(category_note)

    categories = (
        filtered["_category"]
        .value_counts()
        .rename_axis("Category")
        .reset_index(name="Articles")
    )

    fig = px.bar(
        categories,
        x="Category",
        y="Articles",
        color="Category",
        template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("View source statistics"):
        st.dataframe(source_counts, hide_index=True, use_container_width=True)

# -------------------- ARTICLE EXPLORER PAGE --------------------

elif page == "Article Explorer":
    show_metrics(filtered)

    st.divider()
    st.subheader("Find and inspect articles")

    search_query = st.text_input(
        "Search titles, article text, descriptions, sources or URLs",
        placeholder="Try a topic, keyword, source or URL...",
    )

    result = filtered.copy()

    if search_query.strip():
        query = search_query.strip().lower()
        search_columns = [
            "_title", "_text", "_description", "_source", "_url"
        ]

        matches = pd.Series(False, index=result.index)

        for col in search_columns:
            matches |= result[col].str.lower().str.contains(
                query, regex=False, na=False
            )

        result = result[matches]

    st.write(f"**Matching articles:** {len(result):,}")

    display = pd.DataFrame(index=result.index)
    display["Title"] = result["_title"].replace("", "(No title)")
    display["Source"] = result["_source"]
    display["Published At"] = result["_date"].dt.strftime(
        "%Y-%m-%d %H:%M UTC"
    ).fillna("Unknown")
    display["Author"] = result["_author"].replace("", "Unknown")
    display["Category"] = result["_category"]
    display["URL"] = result["_url"]

    st.dataframe(
        display.head(1000),
        hide_index=True,
        use_container_width=True,
        height=470,
        column_config={
            "URL": st.column_config.LinkColumn(
                "Article URL",
                display_text="Open article",
            )
        },
    )

    st.caption("The table displays up to 1,000 matching rows. Download to get all filtered matches.")

    download_df = result.drop(
        columns=[
            "_source", "_title", "_text", "_description",
            "_url", "_author", "_date", "_category",
        ],
        errors="ignore",
    )

    st.download_button(
        "⬇️ Download matching articles as CSV",
        data=download_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="filtered_news_articles.csv",
        mime="text/csv",
        use_container_width=False,
    )

    if not result.empty:
        st.divider()
        st.subheader("Article Preview")

        preview_options = result.index.tolist()[:500]
        selected_index = st.selectbox(
            "Choose an article",
            options=preview_options,
            format_func=lambda idx: (
                result.loc[idx, "_title"][:110]
                if result.loc[idx, "_title"]
                else f"Article row {idx}"
            ),
        )

        article = result.loc[selected_index]

        st.markdown(f"### {article['_title'] or 'Untitled article'}")
        st.caption(
            f"Source: {article['_source']}  |  "
            f"Published: {article['_date'] if pd.notna(article['_date']) else 'Unknown'}"
        )

        if article["_url"]:
            st.markdown(f"[Open original article]({article['_url']})")

        article_text = article["_text"] or article["_description"]

        if article_text:
            st.write(article_text[:12000])
            if len(article_text) > 12000:
                st.caption("Preview shortened to 12,000 characters.")
        else:
            st.info("No article text or description is available for this row.")

# -------------------- DATA QUALITY PAGE --------------------

elif page == "Data Quality":
    st.subheader("Data Quality Overview")
    st.write(
        "This page reports missing values and repeated records in the currently loaded dataset. "
        "It does not automatically delete or repair records."
    )

    total_rows = len(df)
    total_cells = df.shape[0] * df.shape[1]
    missing_cells = int(df.isna().sum().sum())

    # Empty strings are missing for quality reporting too.
    empty_cells = 0
    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            empty_cells += int(df[col].astype("string").str.strip().eq("").fillna(False).sum())

    missing_total = missing_cells + empty_cells
    completeness = (
        max(0, 1 - missing_total / total_cells) * 100
        if total_cells else 0
    )

    duplicate_rows = int(df.duplicated().sum())

    if url_col:
        normalized_urls = (
            safe_text(df[url_col])
            .str.lower()
            .str.rstrip("/")
        )
        nonempty_urls = normalized_urls[normalized_urls != ""]
        duplicate_urls = int(nonempty_urls.duplicated().sum())
    else:
        duplicate_urls = None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Rows", f"{total_rows:,}")
    c2.metric("Missing / Empty Cells", f"{missing_total:,}")
    c3.metric("Completeness", f"{completeness:.2f}%")
    c4.metric("Exact Duplicate Rows", f"{duplicate_rows:,}")

    if duplicate_urls is not None:
        st.metric("Repeated Non-empty URLs", f"{duplicate_urls:,}")

    st.divider()
    st.subheader("Missing Values by Column")

    missing_by_col = pd.DataFrame({
        "Column": df.columns,
        "Missing Values": [
            int(df[col].isna().sum())
            + (
                int(df[col].astype("string").str.strip().eq("").fillna(False).sum())
                if (
                    pd.api.types.is_object_dtype(df[col])
                    or pd.api.types.is_string_dtype(df[col])
                )
                else 0
            )
            for col in df.columns
        ],
    })

    missing_by_col["Missing %"] = (
        missing_by_col["Missing Values"] / total_rows * 100
        if total_rows else 0
    )

    missing_by_col = missing_by_col.sort_values(
        "Missing Values", ascending=False
    )

    fig = px.bar(
        missing_by_col.head(25).sort_values("Missing Values"),
        x="Missing Values",
        y="Column",
        orientation="h",
        template="plotly_white",
        title="Columns with the Most Missing Values",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        missing_by_col,
        hide_index=True,
        use_container_width=True,
    )

    st.download_button(
        "⬇️ Download data quality report",
        data=missing_by_col.to_csv(index=False).encode("utf-8-sig"),
        file_name="news_data_quality_report.csv",
        mime="text/csv",
    )

    st.divider()
    st.subheader("Column Completeness")

    completeness_by_col = missing_by_col.copy()
    completeness_by_col["Completeness %"] = (
        100 - completeness_by_col["Missing %"]
    ).clip(lower=0, upper=100)

    fig = px.bar(
        completeness_by_col.sort_values("Completeness %"),
        x="Completeness %",
        y="Column",
        orientation="h",
        range_x=[0, 100],
        template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)

# -------------------- FOOTER --------------------

st.divider()
st.markdown(
    '<p class="small-note">News Intelligence Dashboard · '
    'Interactive analysis of your selected news dataset</p>',
    unsafe_allow_html=True,
)

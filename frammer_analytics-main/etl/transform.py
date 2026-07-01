"""
transform.py — ETL Layer 3: Clean, enrich, and write processed outputs

What this does:
  1.  Parse hh:mm:ss duration strings → decimal minutes across all aggregate CSVs
  2.  Compute per-dimension KPIs (publish_rate, multiplication_ratio, unpublished_gap)
  3.  Fix the 12 null input_type rows in fact_video (fallback → 'unknown')
  4.  Apportion aggregate user-level durations back to individual fact_video rows
  5.  Melt publishing breakdown (channel × platform) into long format
  6.  Merge monthly counts + durations into one clean time-series DataFrame
  7.  Write all processed DataFrames to data/processed/ as Parquet
  8.  Create a summary_stats table in DuckDB for fast dashboard queries

Run standalone:
    python etl/transform.py

Or import:
    from etl.transform import run_transform
    run_transform(con)
"""

import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import (
    CSV_FILES,
    COLUMN_MAPPINGS,
    DATABASE_PATH,
    NULL_EQUIVALENTS,
    PROCESSED_PATH,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load(key: str) -> pd.DataFrame:
    df = pd.read_csv(CSV_FILES[key], encoding="utf-8")
    df = df.rename(columns={k: v for k, v in COLUMN_MAPPINGS.items() if k in df.columns})
    df = df.replace(NULL_EQUIVALENTS, np.nan)
    return df


def _hms_to_minutes(value) -> float:
    """Convert h:mm:ss or hh:mm:ss (or mm:ss) string → decimal minutes."""
    if pd.isna(value) or str(value).strip() == "":
        return 0.0
    try:
        parts = str(value).strip().split(":")
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
            return round(h * 60 + m + s / 60, 4)
        if len(parts) == 2:
            m, s = int(parts[0]), float(parts[1])
            return round(m + s / 60, 4)
    except (ValueError, TypeError):
        pass
    return 0.0


def _add_kpis(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add publish_rate, multiplication_ratio, unpublished_gap columns.
    Works on any DataFrame that has uploaded_count, created_count, published_count.
    """
    df = df.copy()
    u = pd.to_numeric(df.get("uploaded_count", 0), errors="coerce").fillna(0)
    c = pd.to_numeric(df.get("created_count",  0), errors="coerce").fillna(0)
    p = pd.to_numeric(df.get("published_count", 0), errors="coerce").fillna(0)

    df["publish_rate"]          = (p / c.replace(0, np.nan) * 100).round(2)
    df["multiplication_ratio"]  = (c / u.replace(0, np.nan)).round(4)
    df["unpublished_gap"]       = (c - p).astype(int)
    return df


def _ensure_processed_dir() -> None:
    os.makedirs(PROCESSED_PATH, exist_ok=True)


def _save(df: pd.DataFrame, name: str) -> None:
    """Write a DataFrame to data/processed/<name>.parquet"""
    _ensure_processed_dir()
    path = os.path.join(PROCESSED_PATH, f"{name}.parquet")
    df.to_parquet(path, index=False)
    print(f"       saved → data/processed/{name}.parquet  ({len(df)} rows)")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Aggregate CSV transforms
# ─────────────────────────────────────────────────────────────────────────────

_DIM_DURATION_COLS = {
    "uploaded_duration" : "uploaded_mins",
    "created_duration"  : "created_mins",
    "published_duration": "published_mins",
}


def _transform_aggregate(key: str, dim_col: str) -> pd.DataFrame:
    """
    Generic transform for users / channels / input_types / output_types / languages.
    - Converts duration strings to minutes
    - Casts count cols to int
    - Adds KPI columns
    """
    df = _load(key)
    for src, dst in _DIM_DURATION_COLS.items():
        if src in df.columns:
            df[dst] = df[src].apply(_hms_to_minutes)
            df = df.drop(columns=[src])

    for col in ["uploaded_count", "created_count", "published_count"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df = _add_kpis(df)
    return df


def transform_users()       -> pd.DataFrame:
    return _transform_aggregate("users", "user_name")

def transform_channels()    -> pd.DataFrame:
    return _transform_aggregate("channels", "channel_name")

def transform_input_types() -> pd.DataFrame:
    return _transform_aggregate("input_types", "input_type")

def transform_output_types() -> pd.DataFrame:
    return _transform_aggregate("output_types", "output_type")

def transform_languages()   -> pd.DataFrame:
    return _transform_aggregate("languages", "language")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Monthly time-series (merge counts + durations, parse month label)
# ─────────────────────────────────────────────────────────────────────────────

_MONTH_ORDER = {
    "jan": 1, "feb": 2, "mar": 3,  "apr": 4,
    "may": 5, "jun": 6, "jul": 7,  "aug": 8,
    "sep": 9, "oct": 10,"nov": 11, "dec": 12,
}


def _parse_month_label(label: str):
    """'Apr, 2025' → (month_number=4, year=2025, sort_key=202504)"""
    label = str(label).strip().rstrip(",")
    parts = label.replace(",", "").split()
    if len(parts) == 2:
        abbr = parts[0][:3].lower()
        try:
            year = int(parts[1])
        except ValueError:
            year = 0
        month_num = _MONTH_ORDER.get(abbr, 0)
        sort_key  = year * 100 + month_num
        return month_num, year, sort_key
    return 0, 0, 0


def transform_monthly() -> pd.DataFrame:
    """
    Merge monthly-chart.csv (counts) + month-wise-duration.csv (durations),
    standardise the month label, and sort chronologically.
    """
    counts = _load("monthly").rename(columns={
        "Total Uploaded" : "uploaded_count",
        "Total Created"  : "created_count",
        "Total Published": "published_count",
    })
    durs = _load("monthly_dur").rename(columns={
        "Total Uploaded Duration" : "uploaded_duration",
        "Total Created Duration"  : "created_duration",
        "Total Published Duration": "published_duration",
    })

    df = counts.merge(durs, on="month", how="left")

    for src, dst in _DIM_DURATION_COLS.items():
        if src in df.columns:
            df[dst] = df[src].apply(_hms_to_minutes)
            df = df.drop(columns=[src])

    for col in ["uploaded_count", "created_count", "published_count"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    parsed = df["month"].apply(_parse_month_label)
    df["month_number"] = parsed.apply(lambda t: t[0])
    df["year"]         = parsed.apply(lambda t: t[1])
    df["sort_key"]     = parsed.apply(lambda t: t[2])
    df = df.sort_values("sort_key").drop(columns=["sort_key"]).reset_index(drop=True)

    df = _add_kpis(df)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 3. Publishing platform breakdown (long format)
# ─────────────────────────────────────────────────────────────────────────────

_PLATFORM_COLS = ["Facebook", "Instagram", "Linkedin", "Reels", "Shorts", "X", "Youtube", "Threads"]


def transform_publishing() -> pd.DataFrame:
    """
    Melt channel × platform count + duration into long format:
        channel_name | platform | publish_count | published_mins
    """
    counts = _load("publishing").rename(columns={"Channels": "channel_name"})
    durs   = _load("pub_duration").rename(columns={"Channels": "channel_name"})

    # melt counts
    count_long = counts.melt(
        id_vars="channel_name",
        value_vars=[c for c in _PLATFORM_COLS if c in counts.columns],
        var_name="platform",
        value_name="publish_count",
    )

    # melt durations — duration cols are named "Facebook Duration" etc.
    dur_rename = {f"{p} Duration": p for p in _PLATFORM_COLS}
    durs = durs.rename(columns=dur_rename)
    dur_long = durs.melt(
        id_vars="channel_name",
        value_vars=[c for c in _PLATFORM_COLS if c in durs.columns],
        var_name="platform",
        value_name="published_duration",
    )
    dur_long["published_mins"] = dur_long["published_duration"].apply(_hms_to_minutes)
    dur_long = dur_long.drop(columns=["published_duration"])

    df = count_long.merge(dur_long, on=["channel_name", "platform"], how="left")
    df["publish_count"] = pd.to_numeric(df["publish_count"], errors="coerce").fillna(0).astype(int)

    # drop rows with zero count and zero duration (clean noise)
    df = df[(df["publish_count"] > 0) | (df["published_mins"] > 0)].reset_index(drop=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 4. Video list clean (fix null input_type)
# ─────────────────────────────────────────────────────────────────────────────

def transform_video_list() -> pd.DataFrame:
    """
    Clean the video_list CSV:
    - Fill null input_type with 'unknown'
    - Normalise is_published to a bool
    - Fill null published_platform with 'Not Published'
    - Fill null team_name with 'Unknown'
    """
    df = _load("video_list")

    df["input_type"] = df["input_type"].fillna("unknown")

    df["is_published"] = (
        df["is_published"].astype(str).str.strip().str.lower()
        .map({"yes": True, "true": True, "1": True})
        .notna()
        .where(df["is_published"].astype(str).str.strip().str.lower().isin(["yes", "true", "1"]), False)
    ).astype(bool)

    df["published_platform"] = df["published_platform"].fillna("Not Published")
    df["team_name"]           = df["team_name"].fillna("Unknown")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# 5. DuckDB updates
# ─────────────────────────────────────────────────────────────────────────────

def fix_null_input_types(con: duckdb.DuckDBPyConnection) -> int:
    """
    The 12 rows in fact_video where input_type_id IS NULL get assigned the id
    for 'unknown' (inserting the dimension row first if absent).
    Returns the number of rows updated.
    """
    # ensure 'unknown' exists in dim_input_type
    existing = con.execute(
        "SELECT input_type_id FROM dim_input_type WHERE LOWER(input_type_name) = 'unknown'"
    ).fetchone()

    if existing:
        unknown_id = existing[0]
    else:
        max_id = con.execute("SELECT COALESCE(MAX(input_type_id), 0) FROM dim_input_type").fetchone()[0]
        unknown_id = max_id + 1
        con.execute(
            "INSERT INTO dim_input_type (input_type_id, input_type_name) VALUES (?, ?)",
            [unknown_id, "unknown"],
        )

    updated = con.execute(
        "SELECT COUNT(*) FROM fact_video WHERE input_type_id IS NULL"
    ).fetchone()[0]
    con.execute(
        "UPDATE fact_video SET input_type_id = ? WHERE input_type_id IS NULL",
        [unknown_id],
    )
    return updated


def apportion_user_durations(
    con: duckdb.DuckDBPyConnection,
    users_df: pd.DataFrame,
) -> int:
    """
    Distribute per-user aggregate durations to individual fact_video rows.

    Strategy: per_video_duration = total_user_duration / user_video_count
    This is an approximation — it sets a meaningful non-placeholder value.
    """
    # build a lookup: {user_name → (uploaded_mins, created_mins, published_mins)}
    user_totals = users_df.set_index("user_name")[
        ["uploaded_mins", "created_mins", "published_mins"]
    ].to_dict(orient="index")

    # get per-user video counts from fact_video
    rows = con.execute("""
        SELECT u.user_name, COUNT(*) as cnt, SUM(f.is_published::INT) as pub_cnt
        FROM fact_video f
        JOIN dim_user u ON f.user_id = u.user_id
        GROUP BY u.user_name
    """).fetchall()

    updated = 0
    for user_name, cnt, pub_cnt in rows:
        totals = user_totals.get(user_name)
        if not totals or cnt == 0:
            continue

        per_uploaded  = round(totals["uploaded_mins"]  / cnt, 4)
        per_created   = round(totals["created_mins"]   / cnt, 4)
        # only spread published_mins across published rows
        per_published = (
            round(totals["published_mins"] / pub_cnt, 4) if pub_cnt > 0 else 0.0
        )

        con.execute("""
            UPDATE fact_video
            SET uploaded_mins = ?,
                created_mins  = ?
            WHERE user_id = (
                SELECT user_id FROM dim_user WHERE user_name = ?
            )
        """, [per_uploaded, per_created, user_name])

        con.execute("""
            UPDATE fact_video
            SET published_mins = ?
            WHERE is_published = TRUE
              AND user_id = (
                  SELECT user_id FROM dim_user WHERE user_name = ?
              )
        """, [per_published, user_name])

        updated += cnt

    return updated


def write_summary_stats(con: duckdb.DuckDBPyConnection) -> None:
    """
    Create (or replace) a summary_stats table in DuckDB with all 27 KPIs
    for fast top-level dashboard queries.

    KPIs are computed directly from the raw CSVs (not from fact_video) so
    they reflect the full dataset including any QA rows that were stripped
    from the fact table. Duration figures come from the channels aggregate
    CSV which has the most complete duration data.
    """
    # ── Load raw CSVs ────────────────────────────────────────────────────────
    channels_df = _load("channels")
    users_df    = _load("users")
    langs_df    = _load("languages")
    monthly_df  = _load("monthly")
    pub_df      = _load("publishing")
    pub_dur_df  = _load("pub_duration")
    vl_df       = pd.read_csv(CSV_FILES["video_list"], encoding="utf-8")

    QA_ACCOUNTS_LOCAL = [
        "Test User", "deleteme@frammer.com", "Auto Upload",
        "QA-Ankith", "QA-Aniket", "QA-Bhargavi", "QA-Purushottam", "QA-Amit",
    ]

    # ── Duration helper ──────────────────────────────────────────────────────
    def _to_hours(val):
        if pd.isna(val) or str(val).strip() == "":
            return 0.0
        try:
            p = str(val).strip().split(":")
            if len(p) == 3:
                return int(p[0]) + int(p[1]) / 60 + float(p[2]) / 3600
            if len(p) == 2:
                return int(p[0]) / 60 + float(p[1]) / 3600
        except (ValueError, TypeError):
            pass
        return 0.0

    def _to_secs(val):
        h = _to_hours(val)
        return round(h * 3600, 2)

    # ── 1–3: Core counts ────────────────────────────────────────────────────
    total_uploaded  = int(channels_df["uploaded_count"].sum())
    total_created   = int(channels_df["created_count"].sum())
    total_published = int(channels_df["published_count"].sum())

    # ── 4–6: Rates ──────────────────────────────────────────────────────────
    global_publish_rate       = round(total_published / total_created * 100, 2)
    upload_to_publish_conv    = round(total_published / total_uploaded * 100, 2)
    ai_compute_waste_rate     = round(100 - global_publish_rate, 2)

    # ── 7–8: Duration ───────────────────────────────────────────────────────
    total_server_compute_hrs  = round(
        channels_df["created_duration"].apply(_to_hours).sum(), 2)
    total_published_hrs       = round(
        channels_df["published_duration"].apply(_to_hours).sum(), 4)

    # ── 9–10: Efficiency ratios ──────────────────────────────────────────────
    avg_compute_cost_per_pub  = round(total_created / total_published, 2)
    ai_content_multiplier     = round(total_created / total_uploaded, 2)

    # ── 11–15: Language KPIs ────────────────────────────────────────────────
    en_row = langs_df[langs_df["language"] == "en"].iloc[0]
    hi_row = langs_df[langs_df["language"] == "hi"].iloc[0]
    en_pub_rate = round(en_row["published_count"] / en_row["created_count"] * 100, 2)
    hi_pub_rate = round(hi_row["published_count"] / hi_row["created_count"] * 100, 2)
    en_hi_efficacy_multiplier = round(en_pub_rate / hi_pub_rate, 2)
    en_gen_cost = round(en_row["created_count"] / en_row["published_count"], 0)
    hi_gen_cost = round(hi_row["created_count"] / hi_row["published_count"], 0)

    # ── 16: Channel health ──────────────────────────────────────────────────
    total_channels   = len(channels_df)
    dead_channels    = int((channels_df["published_count"] == 0).sum())
    active_channels  = total_channels - dead_channels
    dead_channel_pct = round(dead_channels / total_channels * 100, 2)
    active_channel_ratio = round(active_channels / total_channels * 100, 2)

    # ── 17: Zero-value users (non-QA) ────────────────────────────────────────
    non_qa = users_df[~users_df["user_name"].isin(QA_ACCOUNTS_LOCAL)]
    zero_value_users = int((non_qa["published_count"] == 0).sum())

    # ── 18: Best performing channel ─────────────────────────────────────────
    channels_df = channels_df.copy()
    channels_df["ch_pub_rate"] = (
        channels_df["published_count"] / channels_df["created_count"] * 100
    ).round(2)
    best_ch_row = channels_df.loc[channels_df["ch_pub_rate"].idxmax()]
    best_channel_name        = str(best_ch_row["channel_name"])
    best_channel_publish_rate = float(best_ch_row["ch_pub_rate"])

    # ── 19: Channel A contribution ──────────────────────────────────────────
    ch_a = channels_df[channels_df["channel_name"] == "A"]
    ch_a_contribution_pct = round(
        float(ch_a["published_count"].values[0]) / total_published * 100, 2
    ) if len(ch_a) else 0.0

    # ── 20: Top volume user (non-QA) ────────────────────────────────────────
    top_vol_user = non_qa.loc[non_qa["uploaded_count"].idxmax(), "user_name"]

    # ── 21: Best efficiency user (non-QA, min 1 publish) ────────────────────
    non_qa_pub = non_qa[non_qa["published_count"] > 0].copy()
    non_qa_pub["eff_rate"] = (
        non_qa_pub["published_count"] / non_qa_pub["created_count"] * 100
    ).round(2)
    best_eff_user     = non_qa_pub.loc[non_qa_pub["eff_rate"].idxmax(), "user_name"]
    best_eff_pub_rate = float(non_qa_pub["eff_rate"].max())

    # ── 22–24: Monthly averages ──────────────────────────────────────────────
    avg_monthly_uploads   = round(float(monthly_df["Total Uploaded"].mean()), 2)
    avg_monthly_created   = round(float(monthly_df["Total Created"].mean()), 2)
    avg_monthly_published = round(float(monthly_df["Total Published"].mean()), 2)

    # ── 25: Peak workload month ──────────────────────────────────────────────
    peak_wl_idx            = monthly_df["Total Created"].idxmax()
    peak_workload_month    = str(monthly_df.loc[peak_wl_idx, "month"])
    peak_workload_clips    = int(monthly_df.loc[peak_wl_idx, "Total Created"])
    peak_slice_ratio       = round(
        monthly_df.loc[peak_wl_idx, "Total Created"] /
        monthly_df.loc[peak_wl_idx, "Total Uploaded"], 2)

    # ── 26: Peak value month ────────────────────────────────────────────────
    peak_val_idx        = monthly_df["Total Published"].idxmax()
    peak_value_month    = str(monthly_df.loc[peak_val_idx, "month"])
    peak_value_pub_count = int(monthly_df.loc[peak_val_idx, "Total Published"])

    # ── 27: Dec→Feb upload surge ────────────────────────────────────────────
    dec_row = monthly_df[monthly_df["month"].str.contains("Dec", na=False)]
    feb_row = monthly_df[monthly_df["month"].str.contains("Feb", na=False)]
    dec_uploads = int(dec_row["Total Uploaded"].values[0]) if len(dec_row) else 0
    feb_uploads = int(feb_row["Total Uploaded"].values[0]) if len(feb_row) else 0
    dec_to_feb_upload_surge_pct = round(
        (feb_uploads - dec_uploads) / dec_uploads * 100, 1) if dec_uploads else 0.0

    # ── 28: YouTube workload (seconds) ──────────────────────────────────────
    youtube_workload_secs = round(
        pub_dur_df["Youtube Duration"].apply(_to_secs).sum(), 0)

    # ── 29: Unknown team attribution ────────────────────────────────────────
    total_vl_rows   = len(vl_df)
    unknown_mask    = (
        vl_df["Team Name"].isna() |
        vl_df["Team Name"].isin(["Unknown", "unknown", "", "None", "N/A", "none"])
    )
    unknown_team_pct = round(unknown_mask.sum() / total_vl_rows * 100, 2)

    # ── Write table ─────────────────────────────────────────────────────────
    con.execute("DROP TABLE IF EXISTS summary_stats")
    con.execute("""
        CREATE TABLE summary_stats (
            -- Core funnel
            total_uploaded              INTEGER,
            total_ai_generated_clips    INTEGER,
            total_published_clips       INTEGER,
            -- Rates
            global_publish_rate         DOUBLE,
            upload_to_publish_conv_rate DOUBLE,
            ai_compute_waste_rate       DOUBLE,
            -- Duration
            total_server_compute_hrs    DOUBLE,
            total_published_hrs         DOUBLE,
            -- Efficiency
            avg_compute_cost_per_pub    DOUBLE,
            ai_content_multiplier       DOUBLE,
            -- Language
            en_hi_efficacy_multiplier   DOUBLE,
            en_publish_rate             DOUBLE,
            hi_publish_rate             DOUBLE,
            en_gen_cost                 DOUBLE,
            hi_gen_cost                 DOUBLE,
            -- Channel health
            dead_channel_pct            DOUBLE,
            zero_value_users            INTEGER,
            best_channel_name           VARCHAR,
            best_channel_publish_rate   DOUBLE,
            ch_a_contribution_pct       DOUBLE,
            active_channel_ratio        DOUBLE,
            -- Users
            top_volume_user             VARCHAR,
            best_efficiency_user        VARCHAR,
            best_efficiency_pub_rate    DOUBLE,
            -- Monthly trends
            avg_monthly_uploads         DOUBLE,
            avg_monthly_created         DOUBLE,
            avg_monthly_published       DOUBLE,
            peak_workload_month         VARCHAR,
            peak_workload_clips         INTEGER,
            peak_slice_ratio            DOUBLE,
            peak_value_month            VARCHAR,
            peak_value_pub_count        INTEGER,
            dec_to_feb_upload_surge_pct DOUBLE,
            -- Platform
            youtube_workload_secs       DOUBLE,
            -- Data quality
            unknown_team_attribution_pct DOUBLE
        )
    """)
    con.execute("""
        INSERT INTO summary_stats VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
    """, [
        total_uploaded, total_created, total_published,
        global_publish_rate, upload_to_publish_conv, ai_compute_waste_rate,
        total_server_compute_hrs, total_published_hrs,
        avg_compute_cost_per_pub, ai_content_multiplier,
        en_hi_efficacy_multiplier, en_pub_rate, hi_pub_rate,
        en_gen_cost, hi_gen_cost,
        dead_channel_pct, zero_value_users,
        best_channel_name, best_channel_publish_rate, ch_a_contribution_pct,
        active_channel_ratio,
        top_vol_user, best_eff_user, best_eff_pub_rate,
        avg_monthly_uploads, avg_monthly_created, avg_monthly_published,
        peak_workload_month, peak_workload_clips, peak_slice_ratio,
        peak_value_month, peak_value_pub_count, dec_to_feb_upload_surge_pct,
        youtube_workload_secs,
        unknown_team_pct,
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Main orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def run_transform(con: duckdb.DuckDBPyConnection | None = None) -> None:
    close_after = con is None
    if con is None:
        con = duckdb.connect(DATABASE_PATH)

    print("=" * 60)
    print("  FRAMMER ANALYTICS — ETL TRANSFORM")
    print("=" * 60)

    # 1. Aggregate CSVs ────────────────────────────────────────────────────────
    print("\n[1/8]  Transforming aggregate CSVs …")
    users_df        = transform_users()
    channels_df     = transform_channels()
    input_types_df  = transform_input_types()
    output_types_df = transform_output_types()
    languages_df    = transform_languages()
    print(f"       users={len(users_df)}  channels={len(channels_df)}  "
          f"input_types={len(input_types_df)}  output_types={len(output_types_df)}  "
          f"languages={len(languages_df)}")

    # 2. Monthly ───────────────────────────────────────────────────────────────
    print("\n[2/8]  Building monthly time-series …")
    monthly_df = transform_monthly()
    print(f"       {len(monthly_df)} months  "
          f"({monthly_df['month'].iloc[0]} → {monthly_df['month'].iloc[-1]})")

    # 3. Publishing breakdown ──────────────────────────────────────────────────
    print("\n[3/8]  Building publishing platform breakdown …")
    publishing_df = transform_publishing()
    print(f"       {len(publishing_df)} active channel × platform combinations")

    # 4. Clean video list ──────────────────────────────────────────────────────
    print("\n[4/8]  Cleaning video list …")
    video_df = transform_video_list()
    null_remaining = video_df["input_type"].isna().sum()
    print(f"       {len(video_df)} rows  |  null input_type remaining: {null_remaining}")

    # 5. Fix nulls in DB ───────────────────────────────────────────────────────
    print("\n[5/8]  Fixing null input_type_id in fact_video …")
    updated = fix_null_input_types(con)
    print(f"       {updated} row(s) updated")

    # 6. Apportion durations ───────────────────────────────────────────────────
    print("\n[6/8]  Apportioning user durations to fact_video …")
    n = apportion_user_durations(con, users_df)
    print(f"       Duration columns updated for {n} fact rows")

    # 7. Summary stats table ───────────────────────────────────────────────────
    print("\n[7/8]  Writing summary_stats table to DuckDB …")
    write_summary_stats(con)
    stats = con.execute("SELECT * FROM summary_stats").fetchdf()
    print(f"       total_uploaded={stats['total_uploaded'].iloc[0]:,}  "
          f"publish_rate={stats['global_publish_rate'].iloc[0]}%  "
          f"compute_hrs={stats['total_server_compute_hrs'].iloc[0]}")

    con.commit()

    # 8. Write processed Parquet files ─────────────────────────────────────────
    print("\n[8/8]  Writing processed Parquet files …")
    _save(users_df,        "users")
    _save(channels_df,     "channels")
    _save(input_types_df,  "input_types")
    _save(output_types_df, "output_types")
    _save(languages_df,    "languages")
    _save(monthly_df,      "monthly")
    _save(publishing_df,   "publishing_platform")
    _save(video_df,        "video_list")

    if close_after:
        con.close()

    print("\n✅  Transform complete.\n")


if __name__ == "__main__":
    run_transform()
"""
analytics.py — all read-only analytics endpoints

Prefix: /api

Routes:
  GET  /api/summary               → overall KPI snapshot
  GET  /api/users                 → per-user breakdown
  GET  /api/channels              → per-channel breakdown
  GET  /api/input-types           → per-input-type breakdown
  GET  /api/output-types          → per-output-type breakdown
  GET  /api/languages             → per-language breakdown
  GET  /api/monthly               → monthly time-series
  GET  /api/publishing-platforms  → channel × platform breakdown
  GET  /api/videos                → paginated video list with filters
"""

import os
import sys
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from config import PROCESSED_PATH, DATABASE_PATH

import duckdb

router = APIRouter(prefix="/api", tags=["analytics"])

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parquet(name: str) -> pd.DataFrame:
    path = os.path.join(PROCESSED_PATH, f"{name}.parquet")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=503,
            detail=f"Processed data not ready: {name}.parquet missing. Run the ETL pipeline first.",
        )
    return pd.read_parquet(path)


def _db_query(sql: str) -> list[dict]:
    con = duckdb.connect(DATABASE_PATH, read_only=True)
    try:
        return con.execute(sql).df().to_dict(orient="records")
    finally:
        con.close()


def _sort_df(df: pd.DataFrame, sort_by: Optional[str], order: str) -> pd.DataFrame:
    if sort_by and sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=(order == "asc"))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/summary
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/summary")
def get_summary():
    """
    Overall KPI snapshot from the summary_stats table:
    - Core Funnel : total uploaded, total ai generated clips, total published clips
    - Rates : global publish rate, upload to convertion rate, ai compute waste
    - Duration : total server compute hours, total published hours
    - Efficiency : average computation time per publish, ai content multiplier
    - Language : English-to-Hindi Efficacy Multiplier, English Publish Rate, Hindi Publish Rate, English Generation Cost, Hindi Generation Cost
    - Channel Health : Dead Channels, Zero-Value Users, Best Performing Channel, Best Channel by Publish Rate, Channel A contribution percentage, Active Channel Ratio
    - Users : Top User by Volume, Best User by efficiency, Best user by publish rate
    - Montly trends: Average monthly uploads, Average monthly created, Average monthly published, Peak workload month, Peak workload clips, Peak slice ratio, Peak value month, Peak value by publish count, December to February upload surge percentage
    - Platform: Youtube Workload in secs
    - Data Quality: Unknown team attribution percentage
     
    """
    rows = _db_query("SELECT * FROM summary_stats")
    if not rows:
        raise HTTPException(status_code=503, detail="summary_stats table is empty. Run ETL first.")
    return rows[0]


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/users
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/users")
def get_users(
    sort_by: Optional[str] = Query(None, description="Column to sort by, e.g. published_count"),
    order:   str            = Query("desc", pattern="^(asc|desc)$"),
    limit:   Optional[int]  = Query(None, ge=1, le=500),
    exclude_qa: bool        = Query(True, description="Exclude QA accounts"),
):
    """Per-user breakdown with counts, durations and KPIs."""
    df = _parquet("users")

    if exclude_qa:
        from config import QA_ACCOUNTS
        df = df[~df["user_name"].isin(QA_ACCOUNTS)]

    df = _sort_df(df, sort_by, order)
    if limit:
        df = df.head(limit)

    return df.fillna(0).to_dict(orient="records")


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/channels
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/channels")
def get_channels(
    sort_by: Optional[str] = Query(None),
    order:   str            = Query("desc", pattern="^(asc|desc)$"),
):
    """Per-channel breakdown with counts, durations and KPIs."""
    df = _parquet("channels")
    df = _sort_df(df, sort_by, order)
    return df.fillna(0).to_dict(orient="records")


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/input-types
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/input-types")
def get_input_types(
    sort_by: Optional[str] = Query(None),
    order:   str            = Query("desc", pattern="^(asc|desc)$"),
):
    """Breakdown by content input type (interview, speech, debate, news bulletin, etc.)."""
    df = _parquet("input_types")
    df = _sort_df(df, sort_by, order)
    return df.fillna(0).to_dict(orient="records")


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/output-types
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/output-types")
def get_output_types(
    sort_by: Optional[str] = Query(None),
    order:   str            = Query("desc", pattern="^(asc|desc)$"),
):
    """Breakdown by output format (reels, shorts, chapters, full package, etc.)."""
    df = _parquet("output_types")
    df = _sort_df(df, sort_by, order)
    return df.fillna(0).to_dict(orient="records")


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/languages
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/languages")
def get_languages(
    sort_by: Optional[str] = Query(None),
    order:   str            = Query("desc", pattern="^(asc|desc)$"),
):
    """Breakdown by content language."""
    df = _parquet("languages")
    df = _sort_df(df, sort_by, order)
    return df.fillna(0).to_dict(orient="records")


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/monthly
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/monthly")
def get_monthly(
    year: Optional[int] = Query(None, description="Filter to a specific year, e.g. 2025"),
):
    """
    Monthly time-series — counts, durations and KPIs sorted chronologically.
    Optionally filtered to a single year.
    """
    df = _parquet("monthly")
    if year:
        df = df[df["year"] == year]
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data for year {year}.")
    return df.fillna(0).to_dict(orient="records")


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/publishing-platforms
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/publishing-platforms")
def get_publishing_platforms(
    channel: Optional[str] = Query(None, description="Filter to a specific channel name"),
):
    """
    Channel × platform publishing breakdown (long format).
    Returns publish count and published duration in minutes per combination.
    """
    df = _parquet("publishing_platform")
    if channel:
        df = df[df["channel_name"].str.lower() == channel.lower()]
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data for channel '{channel}'.")
    df = df.sort_values(["channel_name", "publish_count"], ascending=[True, False])
    return df.fillna(0).to_dict(orient="records")


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/multidimensional
# ─────────────────────────────────────────────────────────────────────────────

_CROSS_PARQUET = {
    frozenset({"channel",    "user"})            : ("cross_channel_x_user",                 "channel_name",       "user_name"),
    frozenset({"channel",    "platform"})         : ("publishing_platform",                  "channel_name",       "platform"),
    frozenset({"user",       "input_type"})       : ("cross_user_x_input_type",              "uploaded_by",        "input_type"),
    frozenset({"user",       "platform"})         : ("cross_user_x_platform",                "uploaded_by",        "published_platform"),
    frozenset({"user",       "published_status"}) : ("cross_user_x_published_status",         "uploaded_by",        "published_status"),
    frozenset({"input_type", "platform"})         : ("cross_input_type_x_platform",           "input_type",         "published_platform"),
    frozenset({"input_type", "published_status"}) : ("cross_input_type_x_published_status",   "input_type",         "published_status"),
}

_ALL_DIMS = sorted({d for combo in _CROSS_PARQUET for d in combo})


@router.get("/multidimensional")
def get_multidimensional_analysis(
    dim1: str = Query(..., description="First dimension.", enum=_ALL_DIMS),
    dim2: str = Query(..., description="Second dimension.", enum=_ALL_DIMS),
):
    """
    Two-dimensional analysis using real pre-aggregated data.

    Valid combinations (order does not matter):
      channel x user, channel x platform,
      user x input_type, user x platform, user x published_status,
      input_type x platform, input_type x published_status
    """
    if dim1 == dim2:
        raise HTTPException(status_code=400, detail="dim1 and dim2 must be different.")

    combo = frozenset({dim1, dim2})
    if combo not in _CROSS_PARQUET:
        valid = [" x ".join(sorted(c)) for c in _CROSS_PARQUET]
        raise HTTPException(
            status_code=400,
            detail=f"'{dim1} x {dim2}' is not supported. Valid pairs: {', '.join(sorted(valid))}",
        )

    parquet_name, col1, col2 = _CROSS_PARQUET[combo]
    df = _parquet(parquet_name)

    rename = {}
    if col1 != dim1: rename[col1] = dim1
    if col2 != dim2: rename[col2] = dim2
    if rename:
        df = df.rename(columns=rename)

    df = df.sort_values([dim1, dim2]).reset_index(drop=True)
    return df.fillna(0).to_dict(orient="records")

# ─────────────────────────────────────────────────────────────────────────────
# GET /api/videos
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/videos")
def get_videos(
    uploaded_by:   Optional[str]  = Query(None, description="Filter by uploader name"),
    input_type:    Optional[str]  = Query(None, description="Filter by input type"),
    is_published:  Optional[bool] = Query(None, description="Filter by publish status"),
    platform:      Optional[str]  = Query(None, description="Filter by published platform"),
    page:          int            = Query(1, ge=1),
    page_size:     int            = Query(50, ge=1, le=500),
):
    """
    Paginated video list with optional filters.
    Returns video metadata: headline, uploader, input type, publish status, platform, URL.
    """
    df = _parquet("video_list")

    if uploaded_by:
        df = df[df["uploaded_by"].str.lower() == uploaded_by.lower()]
    if input_type:
        df = df[df["input_type"].str.lower() == input_type.lower()]
    if is_published is not None:
        df = df[df["is_published"] == is_published]
    if platform:
        df = df[df["published_platform"].str.lower() == platform.lower()]

    total   = len(df)
    start   = (page - 1) * page_size
    end     = start + page_size
    page_df = df.iloc[start:end]

    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     (total + page_size - 1) // page_size,
        "data":      page_df.fillna("").to_dict(orient="records"),
    }
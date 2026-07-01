"""
validation.py — ETL Layer 2: Data-quality checks after ingestion

Checks cover two surfaces:
  A) Raw CSVs  — schema, nulls, negatives, duplicates, logical consistency
  B) DuckDB    — row counts, referential integrity, KPI bounds, QA leakage

Run standalone:
    python etl/validation.py

Or import and call check() from transform.py / scheduler.py:
    from etl.validation import run_validation
    passed = run_validation(con)   # returns True if no FAIL results
"""

import os
import sys
from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import (
    CSV_FILES,
    COLUMN_MAPPINGS,
    DATABASE_PATH,
    NULL_EQUIVALENTS,
    QA_ACCOUNTS,
    REQUIRED_COLUMNS,
)

# ─────────────────────────────────────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────────────────────────────────────

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass
class CheckResult:
    name:    str
    status:  str          # PASS / WARN / FAIL
    message: str
    count:   int = 0      # number of offending rows / items (0 = clean)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load(key: str) -> pd.DataFrame:
    """Load + rename a CSV without removing NULL_EQUIVALENTS (we want to see them)."""
    df = pd.read_csv(CSV_FILES[key], encoding="utf-8")
    df = df.rename(columns={k: v for k, v in COLUMN_MAPPINGS.items() if k in df.columns})
    return df


_COUNT_COLS    = ["uploaded_count", "created_count", "published_count"]
_DURATION_COLS = ["uploaded_duration", "created_duration", "published_duration"]


# ─────────────────────────────────────────────────────────────────────────────
# A) CSV-level checks
# ─────────────────────────────────────────────────────────────────────────────

def check_required_columns(results: list) -> None:
    """All columns listed in REQUIRED_COLUMNS must be present in their CSV."""
    for csv_key, cols in REQUIRED_COLUMNS.items():
        if csv_key not in CSV_FILES:
            continue
        df = _load(csv_key)
        missing = [c for c in cols if c not in df.columns]
        if missing:
            results.append(CheckResult(
                f"schema:{csv_key}",
                FAIL,
                f"Required column(s) missing: {missing}",
                len(missing),
            ))
        else:
            results.append(CheckResult(
                f"schema:{csv_key}",
                PASS,
                f"All required columns present ({cols})",
            ))


def check_null_required(results: list) -> None:
    """
    Nulls in REQUIRED_COLUMNS are reported as WARN (data quality issue, handled
    by transform.py).  The schema check is the FAIL gate for missing columns.
    Exception: video_id and uploaded_by are identity columns — nulls there are FAIL.
    """
    _identity_cols = {"video_id", "uploaded_by"}

    for csv_key, req_cols in REQUIRED_COLUMNS.items():
        if csv_key not in CSV_FILES:
            continue
        df = _load(csv_key)
        df = df.replace(NULL_EQUIVALENTS, np.nan)
        for col in req_cols:
            if col not in df.columns:
                continue
            n = int(df[col].isna().sum())
            if n == 0:
                status, message = PASS, "No nulls"
            elif col in _identity_cols:
                status, message = FAIL, f"{n} null value(s) in identity column"
            else:
                status, message = WARN, f"{n} null value(s) — will be fixed by transform"
            results.append(CheckResult(f"null_required:{csv_key}.{col}", status, message, n))

    # soft nulls in video_list headline (WARN only)
    df = _load("video_list").replace(NULL_EQUIVALENTS, np.nan)
    n = int(df["headline"].isna().sum()) if "headline" in df.columns else 0
    results.append(CheckResult(
        "null_warn:video_list.headline",
        WARN if n > 0 else PASS,
        f"{n} rows missing headline",
        n,
    ))


def check_negative_values(results: list) -> None:
    """Count and duration columns must be >= 0 in all aggregate CSVs."""
    agg_keys = ["users", "channels", "input_types", "output_types", "languages"]
    for key in agg_keys:
        df = _load(key).replace(NULL_EQUIVALENTS, np.nan)
        for col in _COUNT_COLS:
            if col not in df.columns:
                continue
            neg = int((pd.to_numeric(df[col], errors="coerce") < 0).sum())
            results.append(CheckResult(
                f"negative:{key}.{col}",
                FAIL if neg > 0 else PASS,
                f"{neg} negative value(s)" if neg > 0 else "All non-negative",
                neg,
            ))


def check_monotonicity(results: list) -> None:
    """
    In aggregate CSVs: published_count <= created_count <= uploaded_count.
    A violation means the source data is internally inconsistent.
    """
    agg_keys = ["users", "channels", "input_types", "output_types", "languages"]
    for key in agg_keys:
        df = _load(key).replace(NULL_EQUIVALENTS, np.nan)
        for col in _COUNT_COLS:
            df[col] = pd.to_numeric(df.get(col, pd.Series(dtype=float)), errors="coerce")

        if all(c in df.columns for c in ["published_count", "created_count"]):
            n = int((df["published_count"] > df["created_count"]).sum())
            results.append(CheckResult(
                f"monotonicity:{key}.pub_le_created",
                FAIL if n > 0 else PASS,
                f"{n} row(s) where published > created",
                n,
            ))
        if all(c in df.columns for c in ["created_count", "uploaded_count"]):
            n = int((df["created_count"] > df["uploaded_count"]).sum())
            results.append(CheckResult(
                f"monotonicity:{key}.created_le_uploaded",
                WARN if n > 0 else PASS,    # WARN: Frammer can create from re-uploads
                f"{n} row(s) where created > uploaded",
                n,
            ))


def check_duplicate_video_ids(results: list) -> None:
    """Duplicate video_id in video_list is a WARN (same video re-processed)."""
    df = _load("video_list").replace(NULL_EQUIVALENTS, np.nan)
    if "video_id" not in df.columns:
        return
    total = len(df)
    unique = df["video_id"].dropna().nunique()
    dupes  = int(df["video_id"].dropna().duplicated().sum())
    results.append(CheckResult(
        "duplicates:video_list.video_id",
        WARN if dupes > 0 else PASS,
        f"{dupes} duplicate video_id(s) out of {total} rows",
        dupes,
    ))


def check_publish_consistency(results: list) -> None:
    """
    Published videos (is_published='Yes') should have a published_platform.
    A missing platform on a published video is a WARN.
    """
    df = _load("video_list").replace(NULL_EQUIVALENTS, np.nan)
    if "is_published" not in df.columns or "published_platform" not in df.columns:
        return
    published_mask   = df["is_published"].str.strip().str.lower().eq("yes")
    platform_missing = published_mask & df["published_platform"].isna()
    n = int(platform_missing.sum())
    results.append(CheckResult(
        "consistency:published_without_platform",
        WARN if n > 0 else PASS,
        f"{n} published video(s) missing published_platform",
        n,
    ))


# ─────────────────────────────────────────────────────────────────────────────
# B) DuckDB checks
# ─────────────────────────────────────────────────────────────────────────────

def check_table_row_counts(con: duckdb.DuckDBPyConnection, results: list) -> None:
    """Every table in the star schema must have at least 1 row after ingestion."""
    tables = [
        "dim_user", "dim_channel", "dim_input_type",
        "dim_output_type", "dim_language", "dim_date", "fact_video",
    ]
    for table in tables:
        try:
            n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            results.append(CheckResult(
                f"rowcount:{table}",
                PASS if n > 0 else FAIL,
                f"{n} row(s)",
                n,
            ))
        except Exception as exc:
            results.append(CheckResult(f"rowcount:{table}", FAIL, str(exc), 0))


def check_referential_integrity(con: duckdb.DuckDBPyConnection, results: list) -> None:
    """
    Orphaned FKs in fact_video: any non-NULL FK that has no matching dim row.
    Reports as WARN (NULLs are acceptable — not all videos have channel/language data).
    """
    fk_checks = {
        "user_id"       : "dim_user",
        "channel_id"    : "dim_channel",
        "input_type_id" : "dim_input_type",
        "output_type_id": "dim_output_type",
        "language_id"   : "dim_language",
        "date_id"       : "dim_date",
    }
    pk_cols = {
        "dim_user"        : "user_id",
        "dim_channel"     : "channel_id",
        "dim_input_type"  : "input_type_id",
        "dim_output_type" : "output_type_id",
        "dim_language"    : "language_id",
        "dim_date"        : "date_id",
    }
    for fk_col, dim_table in fk_checks.items():
        pk_col = pk_cols[dim_table]
        try:
            n = con.execute(f"""
                SELECT COUNT(*) FROM fact_video f
                WHERE f.{fk_col} IS NOT NULL
                  AND f.{fk_col} NOT IN (SELECT {pk_col} FROM {dim_table})
            """).fetchone()[0]
            results.append(CheckResult(
                f"fk:fact_video.{fk_col}",
                WARN if n > 0 else PASS,
                f"{n} orphaned FK value(s)" if n > 0 else "Referential integrity OK",
                n,
            ))
        except Exception as exc:
            results.append(CheckResult(f"fk:fact_video.{fk_col}", FAIL, str(exc), 0))


def check_kpi_bounds(con: duckdb.DuckDBPyConnection, results: list) -> None:
    """publish_rate must be 0–100; multiplication_ratio must be > 0."""
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM fact_video WHERE publish_rate < 0 OR publish_rate > 100"
        ).fetchone()[0]
        results.append(CheckResult(
            "kpi_bounds:publish_rate",
            FAIL if n > 0 else PASS,
            f"{n} row(s) outside [0, 100]" if n > 0 else "All values in range",
            n,
        ))
    except Exception as exc:
        results.append(CheckResult("kpi_bounds:publish_rate", FAIL, str(exc), 0))

    try:
        n = con.execute(
            "SELECT COUNT(*) FROM fact_video WHERE multiplication_ratio IS NOT NULL AND multiplication_ratio <= 0"
        ).fetchone()[0]
        results.append(CheckResult(
            "kpi_bounds:multiplication_ratio",
            FAIL if n > 0 else PASS,
            f"{n} row(s) with ratio <= 0" if n > 0 else "All values positive",
            n,
        ))
    except Exception as exc:
        results.append(CheckResult("kpi_bounds:multiplication_ratio", FAIL, str(exc), 0))


def check_qa_account_leakage(con: duckdb.DuckDBPyConnection, results: list) -> None:
    """
    QA accounts should be flagged in dim_user (is_qa_account=TRUE) and should NOT
    appear as fact_video rows (they were filtered during ingestion).
    """
    try:
        qa_in_fact = con.execute("""
            SELECT COUNT(*) FROM fact_video f
            JOIN dim_user u ON f.user_id = u.user_id
            WHERE u.is_qa_account = TRUE
        """).fetchone()[0]
        results.append(CheckResult(
            "qa_leakage:fact_video",
            FAIL if qa_in_fact > 0 else PASS,
            f"{qa_in_fact} QA-account row(s) found in fact_video" if qa_in_fact > 0
            else "No QA accounts in fact_video",
            qa_in_fact,
        ))
    except Exception as exc:
        results.append(CheckResult("qa_leakage:fact_video", FAIL, str(exc), 0))


def check_team_name_coverage(con: duckdb.DuckDBPyConnection, results: list) -> None:
    """WARN if >50 % of fact_video rows have team_name_quality='Missing'."""
    try:
        total   = con.execute("SELECT COUNT(*) FROM fact_video").fetchone()[0]
        missing = con.execute(
            "SELECT COUNT(*) FROM fact_video WHERE team_name_quality = 'Missing'"
        ).fetchone()[0]
        pct = round(missing / total * 100, 1) if total > 0 else 0.0
        results.append(CheckResult(
            "coverage:team_name",
            WARN if pct > 50 else PASS,
            f"{pct}% of rows have missing team_name ({missing}/{total})",
            missing,
        ))
    except Exception as exc:
        results.append(CheckResult("coverage:team_name", FAIL, str(exc), 0))


# ─────────────────────────────────────────────────────────────────────────────
# Report printer
# ─────────────────────────────────────────────────────────────────────────────

def _print_report(results: list[CheckResult]) -> bool:
    """Print a formatted report. Returns True if no FAIL results."""
    passes = [r for r in results if r.status == PASS]
    warns  = [r for r in results if r.status == WARN]
    fails  = [r for r in results if r.status == FAIL]

    STATUS_ICON = {PASS: "✅", WARN: "⚠️ ", FAIL: "❌"}

    print("\n" + "=" * 65)
    print("  VALIDATION REPORT")
    print("=" * 65)

    if fails:
        print("\n── FAILURES ───────────────────────────────────────────────")
        for r in fails:
            print(f"  {STATUS_ICON[FAIL]}  {r.name}")
            print(f"        {r.message}")

    if warns:
        print("\n── WARNINGS ───────────────────────────────────────────────")
        for r in warns:
            print(f"  {STATUS_ICON[WARN]}  {r.name}")
            print(f"        {r.message}")

    print("\n── PASSED ─────────────────────────────────────────────────")
    for r in passes:
        print(f"  {STATUS_ICON[PASS]}  {r.name:<45}  {r.message}")

    print("\n" + "─" * 65)
    print(f"  Total: {len(results)} checks  │  "
          f"✅ {len(passes)} passed  │  "
          f"⚠️  {len(warns)} warnings  │  "
          f"❌ {len(fails)} failures")
    print("=" * 65 + "\n")

    return len(fails) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_validation(con: duckdb.DuckDBPyConnection | None = None) -> bool:
    """
    Run all validation checks.

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection, optional
        An open connection.  If None, a new connection is opened and closed
        internally (useful when running standalone).

    Returns
    -------
    bool
        True if no FAIL-level checks were found.
    """
    close_after = con is None
    if con is None:
        con = duckdb.connect(DATABASE_PATH)

    results: list[CheckResult] = []

    print("Running CSV checks …")
    check_required_columns(results)
    check_null_required(results)
    check_negative_values(results)
    check_monotonicity(results)
    check_duplicate_video_ids(results)
    check_publish_consistency(results)

    print("Running DuckDB checks …")
    check_table_row_counts(con, results)
    check_referential_integrity(con, results)
    check_kpi_bounds(con, results)
    check_qa_account_leakage(con, results)
    check_team_name_coverage(con, results)

    if close_after:
        con.close()

    return _print_report(results)


if __name__ == "__main__":
    ok = run_validation()
    sys.exit(0 if ok else 1)

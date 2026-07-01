"""
etl.py — ETL trigger endpoint

Prefix: /api/etl

Routes:
  POST /api/etl/run        → trigger full pipeline (ingestion → validation → transform)
  GET  /api/etl/status     → last run status and timestamp
"""

import os
import sys
import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

router = APIRouter(prefix="/api/etl", tags=["etl"])

# ─────────────────────────────────────────────────────────────────────────────
# In-memory run state  (single-process; replace with Redis/DB for multi-worker)
# ─────────────────────────────────────────────────────────────────────────────

_state: dict = {
    "status"     : "idle",       # idle | running | success | failed
    "started_at" : None,
    "finished_at": None,
    "message"    : "No run yet.",
    "lock"       : threading.Lock(),
}


def _run_pipeline_task(force: bool) -> None:
    """Background task: runs the full ETL pipeline and updates _state."""
    import duckdb
    from config import DATABASE_PATH
    from etl.ingestion.registry import FileRegistry
    from etl.ingestion.backfill import run_backfill
    conn = duckdb.connect(DATABASE_PATH)
    registry = FileRegistry()

    run_backfill("./data/raw", registry, conn)
    conn.close()
    from etl.validation import run_validation
    from etl.transform  import run_transform

    with _state["lock"]:
        _state["status"]      = "running"
        _state["started_at"]  = datetime.utcnow().isoformat()
        _state["finished_at"] = None
        _state["message"]     = "Pipeline running …"

    try:
        run_ingestion()

        con    = duckdb.connect(DATABASE_PATH)
        passed = run_validation(con)
        con.close()

        if not passed and not force:
            with _state["lock"]:
                _state["status"]      = "failed"
                _state["finished_at"] = datetime.utcnow().isoformat()
                _state["message"]     = "Validation reported FAIL-level issues. Transform skipped."
            return

        run_transform()

        with _state["lock"]:
            _state["status"]      = "success"
            _state["finished_at"] = datetime.utcnow().isoformat()
            _state["message"]     = "Pipeline completed successfully."

    except Exception as exc:
        with _state["lock"]:
            _state["status"]      = "failed"
            _state["finished_at"] = datetime.utcnow().isoformat()
            _state["message"]     = f"Pipeline error: {exc}"


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/run")
def trigger_pipeline(
    background_tasks: BackgroundTasks,
    force: bool = False,
):
    """
    Trigger the full ETL pipeline in the background:
    ingestion → validation → transform.

    - Returns immediately with a 202 Accepted response.
    - Poll GET /api/etl/status to check progress.
    - Pass `?force=true` to continue even if validation has FAIL-level issues.
    """
    with _state["lock"]:
        if _state["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail="Pipeline is already running. Check /api/etl/status.",
            )

    background_tasks.add_task(_run_pipeline_task, force)
    return {
        "accepted": True,
        "message":  "ETL pipeline started. Poll /api/etl/status for progress.",
    }


@router.get("/status")
def get_pipeline_status():
    """Return the status and timing of the last ETL run."""
    with _state["lock"]:
        return {
            "status"     : _state["status"],
            "started_at" : _state["started_at"],
            "finished_at": _state["finished_at"],
            "message"    : _state["message"],
        }

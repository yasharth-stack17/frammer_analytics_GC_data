"""
main.py — FastAPI application entry point

Start the server:
    uvicorn api.main:app --reload --host localhost --port 8000

Or via config values:
    uvicorn api.main:app --reload --host $API_HOST --port $API_PORT
"""

import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import API_HOST, API_PORT
from api.routes.analytics import router as analytics_router
from api.routes.etl       import router as etl_router

# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       ="Frammer Analytics API",
    description ="Analytics API for the Frammer content platform.",
    version     ="1.0.0",
    docs_url    ="/docs",
    redoc_url   ="/redoc",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# Allow the dashboard (and local dev) to call the API.
# Tighten origins in production to your specific dashboard domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(analytics_router)
app.include_router(etl_router)


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", tags=["health"])
def health():
    """Simple health-check endpoint."""
    return {"status": "ok", "service": "frammer-analytics-api"}


@app.get("/health", tags=["health"])
def health_detailed():
    """Detailed health — checks whether processed data and DB exist."""
    import duckdb
    from config import DATABASE_PATH, PROCESSED_PATH

    db_ok      = os.path.exists(DATABASE_PATH)
    parquet_ok = os.path.isdir(PROCESSED_PATH) and any(
        f.endswith(".parquet") for f in os.listdir(PROCESSED_PATH)
    )

    detail: dict = {
        "database_exists"       : db_ok,
        "processed_data_exists" : parquet_ok,
    }

    if db_ok:
        try:
            con = duckdb.connect(DATABASE_PATH, read_only=True)
            detail["fact_video_rows"] = con.execute(
                "SELECT COUNT(*) FROM fact_video"
            ).fetchone()[0]
            con.close()
        except Exception as exc:
            detail["db_error"] = str(exc)

    detail["ready"] = db_ok and parquet_ok
    return detail


# ─────────────────────────────────────────────────────────────────────────────
# Dev runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host   =str(API_HOST),
        port   =int(API_PORT),
        reload =True,
    )

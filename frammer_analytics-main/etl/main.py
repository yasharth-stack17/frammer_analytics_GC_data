import os
import time
import argparse
import logging
import duckdb
from contextlib import asynccontextmanager
from fastapi import FastAPI

from ingestion.registry import FileRegistry
from ingestion.backfill import run_backfill
from ingestion.watcher import start_watcher

# ── Logging setup ────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

WATCH_DIR = "./data/raw"
DB_PATH   = "frammer_analytics.duckdb"
REG_PATH  = "registry.db"

# ── CLI argument parsing ─────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Frammer Analytics Pipeline",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Wipe DuckDB and registry, then reprocess all CSVs from scratch.\n"
            "Use this when the schema changes or data is corrupted."
        )
    )
    parser.add_argument(
        "--watch-only",
        action="store_true",
        help=(
            "Skip backfill on startup. Only watch for new/changed files.\n"
            "Use this if DB is already in sync and you just want the watcher running."
        )
    )
    return parser.parse_args()

# ── Reset helper ─────────────────────────────────────────────────────

def wipe_state(db_path: str, reg_path: str):
    for path, label in [(db_path, "DuckDB"), (reg_path, "Registry")]:
        if os.path.exists(path):
            os.remove(path)
            logger.warning(f"{label} wiped: {path}")
        else:
            logger.info(f"{label} not found, nothing to wipe: {path}")

# ── FastAPI lifespan ─────────────────────────────────────────────────

def create_app(args) -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ── STARTUP ──────────────────────────────────────────────────
        logger.info("=== Frammer Analytics Pipeline starting ===")

        if args.reset:
            logger.warning("--reset: wiping all state...")
            wipe_state(DB_PATH, REG_PATH)

        # Ensure watch directory exists
        os.makedirs(WATCH_DIR, exist_ok=True)

        # Init shared resources
        conn     = duckdb.connect(DB_PATH)
        registry = FileRegistry(REG_PATH)

        # Store on app.state so API routes can access them later
        app.state.conn     = conn
        app.state.registry = registry

        # Backfill — process all existing CSVs unless --watch-only
        if not args.watch_only:
            run_backfill(
                watch_dir=WATCH_DIR,
                registry=registry,
                duckdb_conn=conn,
                force=args.reset
            )
        else:
            logger.info("--watch-only: skipping backfill.")

        # Start live file watcher
        observer = start_watcher(WATCH_DIR, registry, conn)
        app.state.observer = observer

        logger.info("=== Pipeline ready ===")

        yield  # ← App is live and serving requests from here

        # ── SHUTDOWN ─────────────────────────────────────────────────
        logger.info("=== Shutting down ===")
        observer.stop()
        observer.join()
        conn.close()
        logger.info("Watcher stopped. DuckDB connection closed. Bye.")

    app = FastAPI(
        title="Frammer Analytics API",
        version="1.0.0",
        lifespan=lifespan
    )

    return app

# ── Entry point ──────────────────────────────────────────────────────

args = parse_args()
app  = create_app(args)   # uvicorn imports this 'app' object

# For direct python main.py execution (development only)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

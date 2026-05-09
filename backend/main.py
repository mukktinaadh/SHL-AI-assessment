"""
FastAPI backend for the SHL Assessment Recommender.

Endpoints:
  GET  /health  → {"status": "ok"}
  POST /chat    → Accepts ChatRequest, returns ChatResponse

Startup:
  - Loads catalog.json into app.state.catalog
  - Loads ChromaDB vector index into app.state.collection
  - Validates all entries have a url field
"""

import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent import run_agent
from retriever import load_index
from schemas import ChatRequest, ChatResponse

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths — auto-detect Render persistent disk at /data
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
RENDER_DATA_DIR = "/data"

if os.path.isdir(RENDER_DATA_DIR) and not os.getenv("CATALOG_PATH"):
    # Running on Render with persistent disk mounted
    _default_catalog = os.path.join(RENDER_DATA_DIR, "catalog.json")
    _default_chroma = os.path.join(RENDER_DATA_DIR, "chroma_db")
    logger.info("Detected Render disk at %s — using persistent paths", RENDER_DATA_DIR)
else:
    # Local development
    _default_catalog = os.path.join(BACKEND_DIR, "data", "catalog.json")
    _default_chroma = os.path.join(BACKEND_DIR, "data", "chroma_db")

CATALOG_PATH = os.getenv("CATALOG_PATH", _default_catalog)
CHROMA_PATH = os.getenv("CHROMA_PATH", _default_chroma)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load catalog and ChromaDB collection into app.state on startup."""

    # --- Load catalog.json ---
    logger.info("Loading catalog from %s ...", CATALOG_PATH)
    if not os.path.exists(CATALOG_PATH):
        logger.error("catalog.json not found at %s — run scraper.py first", CATALOG_PATH)
        app.state.catalog = []
    else:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            app.state.catalog = json.load(f)
        logger.info("Loaded %d assessments into catalog", len(app.state.catalog))

        # Validate: warn for any item missing a url
        for i, item in enumerate(app.state.catalog):
            if not item.get("url"):
                logger.warning("Catalog item %d (%s) is missing a url field", i, item.get("name", "UNKNOWN"))

    # --- Load ChromaDB index ---
    logger.info("Loading ChromaDB index from %s ...", CHROMA_PATH)
    try:
        app.state.collection = load_index(CHROMA_PATH)
    except Exception as exc:
        logger.error("Failed to load ChromaDB index: %s — run scripts/build_index.py first", exc)
        app.state.collection = None

    yield  # app is running

    logger.info("Shutting down.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="SHL Assessment Recommender",
    description="Conversational AI agent for SHL Individual Test Solutions",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow all origins (PRD Section 14 Step 4)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return 422 with structured error detail on request validation failures."""
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc.errors())},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    """Readiness probe. Returns {"status": "ok"} with HTTP 200."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Core conversational endpoint.

    Accepts a ChatRequest (list of messages), returns a ChatResponse
    with reply text, recommendations, and end_of_conversation flag.
    """
    if app.state.collection is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "Assessment index is not loaded. Please try again later."},
        )

    try:
        return run_agent(request, app.state.catalog, app.state.collection)
    except Exception as exc:
        logger.exception("Unhandled error in /chat: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal error"},
        )

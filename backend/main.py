"""
main.py — JamaicaHealthOps FastAPI backend.

Start the server:
    uvicorn backend.main:app --reload --port 8000

Interactive docs:
    http://localhost:8000/docs   (Swagger UI)
    http://localhost:8000/redoc

Environment variables:
    DS_DATA_PATH     Path to the data/ folder in the DS project.
                     When set, the API loads live CSV files instead of
                     the embedded snapshots.
                     e.g.  export DS_DATA_PATH=../data

    DS_PROJECT_PATH  Path to the DS project root (for importing src/ modules).
                     e.g.  export DS_PROJECT_PATH=..
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import beds, forecast, optimise, inflow

app = FastAPI(
    title="JamaicaHealthOps API",
    description=(
        "Hospital bed demand forecasting and capacity optimisation "
        "for the Jamaican public health network.\n\n"
        "**DS project mapping**\n"
        "- `GET /api/beds`      → hospitals.csv / live census\n"
        "- `GET /api/inflow`    → src/synthetic_data_creation.py\n"
        "- `GET /api/forecast`  → 03_Prophet_Forecasting.ipynb / data/forecast_data.csv\n"
        "- `POST /api/optimise` → 04_Optimization.ipynb (PuLP functions)\n"
    ),
    version="0.1.0",
)

# ── CORS — allow all origins for local Electron dev ──────────────────────────
# Tighten to specific origins before any network deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(beds.router)
app.include_router(forecast.router)
app.include_router(optimise.router)
app.include_router(inflow.router)


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "service": "JamaicaHealthOps API", "version": "0.1.0"}


@app.get("/", tags=["System"])
def root():
    return {
        "message": "JamaicaHealthOps API is running",
        "docs":    "/docs",
        "health":  "/health",
    }

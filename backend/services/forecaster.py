"""
services/forecaster.py
Wired to 03_Prophet_Forecasting.ipynb — exact model config reproduced.

Prophet config from notebook:
  - yearly_seasonality=True
  - weekly_seasonality=True
  - daily_seasonality=False
  - forecast horizon: 60 days
  - input cols: Date → ds, Predicted_Arrivals → y, grouped by Facility_ID
"""

import os
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data loader
# ---------------------------------------------------------------------------

def _load_arrivals_df() -> Optional[pd.DataFrame]:
    """
    Load synthetic_hospital_arrivals.csv from DS_DATA_PATH if set.
    Returns None if the env var is missing or the file doesn't exist.
    """
    data_path = os.getenv("DS_DATA_PATH")
    if not data_path:
        return None

    csv_path = Path(data_path) / "synthetic_hospital_arrivals.csv"
    if not csv_path.exists():
        logger.warning(f"Arrivals CSV not found at {csv_path}")
        return None

    df = pd.read_csv(csv_path, parse_dates=["Date"])
    logger.info(f"Loaded {len(df)} rows from {csv_path}")
    return df


# ---------------------------------------------------------------------------
# Core forecast function (mirrors notebook logic verbatim)
# ---------------------------------------------------------------------------

def run_prophet_forecast(
    merge_df: pd.DataFrame,
    periods: int = 60,
) -> pd.DataFrame:
    """
    Reproduce 03_Prophet_Forecasting.ipynb cell 0 exactly.

    Parameters
    ----------
    merge_df : DataFrame with columns [Date, Facility_ID, Predicted_Arrivals]
    periods  : forecast horizon in days (default 60, matching notebook)

    Returns
    -------
    forecast_data : concatenated Prophet forecast for all facilities,
                    with Facility_ID column added.
    """
    try:
        from prophet import Prophet  # suppress Stan startup noise
        import logging as _log
        _log.getLogger("prophet").setLevel(_log.WARNING)
        _log.getLogger("cmdstanpy").setLevel(_log.WARNING)
    except ImportError:
        raise RuntimeError(
            "prophet is not installed. Run: pip install prophet"
        )

    merge_df = merge_df.copy()
    merge_df["Date"] = pd.to_datetime(merge_df["Date"])
    merge_df["Predicted_Arrivals"] = pd.to_numeric(
        merge_df["Predicted_Arrivals"], errors="coerce"
    )

    facility_ids = merge_df["Facility_ID"].unique()
    all_forecasts = []

    for facility in facility_ids:
        facility_data = merge_df[merge_df["Facility_ID"] == facility]

        prophet_df = (
            facility_data[["Date", "Predicted_Arrivals"]]
            .rename(columns={"Date": "ds", "Predicted_Arrivals": "y"})
            .dropna()
        )

        if len(prophet_df) < 2:
            logger.warning(f"Skipping facility {facility}: insufficient data")
            continue

        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
        )
        model.fit(prophet_df)

        future = model.make_future_dataframe(periods=periods)
        forecast = model.predict(future)

        forecast["Facility_ID"] = facility
        all_forecasts.append(forecast)

    if not all_forecasts:
        raise ValueError("No forecasts generated — check your input data.")

    forecast_data = pd.concat(all_forecasts, ignore_index=True)
    return forecast_data


# ---------------------------------------------------------------------------
# API-facing entry point
# ---------------------------------------------------------------------------

def get_forecast(
    facility_id: Optional[str] = None,
    periods: int = 60,
    scenario_multiplier: float = 1.0,
) -> list[dict]:
    """
    Load data → run Prophet → return JSON-serialisable list of forecast rows.

    Parameters
    ----------
    facility_id         : filter to a single facility (None = all)
    periods             : forecast horizon in days
    scenario_multiplier : multiply yhat/yhat_lower/yhat_upper by this factor
                          (Normal=1.0, FluSeason=1.1, Outbreak=1.3, Disaster=1.5)
    """
    merge_df = _load_arrivals_df()

    if merge_df is None:
        # Fallback: synthetic stub so the API stays up without real data
        logger.warning("DS_DATA_PATH not set — returning stub forecast")
        return _stub_forecast(facility_id, periods, scenario_multiplier)

    if facility_id:
        merge_df = merge_df[merge_df["Facility_ID"] == facility_id]
        if merge_df.empty:
            raise ValueError(f"No data found for facility_id={facility_id!r}")

    forecast_data = run_prophet_forecast(merge_df, periods=periods)

    # Apply scenario multiplier to prediction columns
    for col in ("yhat", "yhat_lower", "yhat_upper"):
        if col in forecast_data.columns:
            forecast_data[col] = (forecast_data[col] * scenario_multiplier).clip(lower=0)

    # Return only the columns the frontend needs
    keep = ["ds", "Facility_ID", "yhat", "yhat_lower", "yhat_upper", "trend"]
    keep = [c for c in keep if c in forecast_data.columns]
    result = forecast_data[keep].rename(columns={"ds": "date"})
    result["date"] = result["date"].dt.strftime("%Y-%m-%d")

    return result.to_dict(orient="records")


# ---------------------------------------------------------------------------
# Stub (used when DS_DATA_PATH is not configured)
# ---------------------------------------------------------------------------

def _stub_forecast(
    facility_id: Optional[str],
    periods: int,
    multiplier: float,
) -> list[dict]:
    """
    Returns a flat ramp forecast so the frontend renders something
    even before real data is wired in.
    """
    base_date = datetime.today()
    facilities = [facility_id] if facility_id else ["FAC_001", "FAC_002", "FAC_003"]
    rows = []
    for fac in facilities:
        for i in range(periods):
            date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
            yhat = round((20 + i * 0.1) * multiplier, 2)
            rows.append(
                {
                    "date": date,
                    "Facility_ID": fac,
                    "yhat": yhat,
                    "yhat_lower": round(yhat * 0.85, 2),
                    "yhat_upper": round(yhat * 1.15, 2),
                    "trend": yhat,
                }
            )
    return rows

# Alias so routers and optimizer can import run_forecast as before
def run_forecast(req) -> "ForecastResponse":
    from backend.models.schemas import ForecastResponse, ForecastPoint
    from backend.services.hospitals import FACILITY_MAP
    from datetime import datetime

    records = get_forecast(
        facility_id=req.facility_id,
        periods=60,
        scenario_multiplier=req.seasonality_factor,
    )

    # Deduplicate — take the most recent yhat per facility
    seen = {}
    for r in records:
        fid = r["Facility_ID"]
        if fid not in seen:
            seen[fid] = r

    forecasts = []
    for fid, r in seen.items():
        fac = FACILITY_MAP.get(fid)
        forecasts.append(ForecastPoint(
            facility_id=fid,
            name=fac.name if fac else fid,
            parish=fac.parish if fac else "",
            beds=fac.beds_z999 if fac else 0,
            yhat=round(r["yhat"], 2),
            yhat_lower=round(r.get("yhat_lower", 0), 2),
            yhat_upper=round(r.get("yhat_upper", 0), 2),
        ))

    return ForecastResponse(forecasts=forecasts, timestamp=datetime.utcnow())
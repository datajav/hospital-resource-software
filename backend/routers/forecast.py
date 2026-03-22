"""GET /api/forecast — Prophet demand forecast per facility."""

from fastapi import APIRouter, Query
from typing import Optional
from backend.models.schemas import ForecastRequest, ForecastResponse
from backend.services.forecaster import run_forecast

router = APIRouter(prefix="/api/forecast", tags=["Forecast"])


@router.get("", response_model=ForecastResponse, summary="Prophet demand forecast")
def get_forecast(
    facility_id: Optional[str] = Query(None, description="Facility code, e.g. '01-02' (omit for all)"),
    seasonality:  float         = Query(1.0,  description="Seasonality multiplier 0.5–2.0", ge=0.5, le=2.0),
):
    """
    Returns yhat (Prophet forecast) per active facility.

    DS hook: services/forecaster.py → run_forecast().
    Set DS_DATA_PATH to load from data/forecast_data.csv automatically.
    """
    return run_forecast(ForecastRequest(facility_id=facility_id, seasonality_factor=seasonality))


@router.post("", response_model=ForecastResponse, summary="Prophet forecast (POST body)")
def post_forecast(req: ForecastRequest):
    """Same as GET but accepts a JSON body — useful from the Electron front-end."""
    return run_forecast(req)

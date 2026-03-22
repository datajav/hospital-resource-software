"""GET /api/inflow — Poisson arrival rates with seasonal variation."""

from fastapi import APIRouter, Query
from typing import Optional
from datetime import date
from backend.models.schemas import InflowRequest, InflowResponse
from backend.services.inflow import get_inflow

router = APIRouter(prefix="/api/inflow", tags=["Inflow"])


@router.get("", response_model=InflowResponse, summary="Synthetic Poisson inflow by facility/date range")
def get_inflow_rates(
    facility_id:       Optional[str]   = Query(None,  description="Facility code (omit for all)"),
    seasonality:       float            = Query(1.0,   ge=0.5, le=2.0),
    start_date:        Optional[date]   = Query(None,  description="YYYY-MM-DD"),
    end_date:          Optional[date]   = Query(None,  description="YYYY-MM-DD"),
):
    """
    Returns daily ER / ICU / Maternity arrival counts per facility,
    using the same Poisson + seasonality logic as synthetic_data_creation.py.

    DS hook: services/inflow.py.
    Set DS_DATA_PATH to load directly from data/synthetic_hospital_arrivals.csv.
    """
    return get_inflow(InflowRequest(
        facility_id=facility_id,
        seasonality_factor=seasonality,
        start_date=start_date,
        end_date=end_date,
    ))

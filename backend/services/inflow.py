"""
inflow.py — Wraps the Poisson arrival generation from the DS project.

DS source: src/synthetic_data_creation.py  (and 02_SyntheticData.ipynb)

Logic reproduced here:
  - Departments: ER (lambda=20), ICU (lambda=10), Maternity (lambda=5)
  - Monthly seasonal factors: Jan=1.0, Feb=1.3, Mar=1.2, Apr=0.9
  - arrivals = Poisson(lambda * season_factor)

HOW TO CONNECT YOUR DS CODE:
  Option A — import the function directly:
      import sys, os
      sys.path.insert(0, os.environ.get("DS_PROJECT_PATH", "../../ds-project"))
      from src.synthetic_data_creation import generate_arrivals
      # then call generate_arrivals(...) instead of the stub below

  Option B — point DS_DATA_PATH at data/ and load the pre-generated CSV:
      os.environ["DS_DATA_PATH"] = "../../ds-project/data"
  The service will load synthetic_hospital_arrivals.csv automatically.
"""

import os
import csv
import io
import random
from datetime import date, timedelta
from backend.models.schemas import (
    DepartmentInflow, FacilityDailyInflow, InflowRequest, InflowResponse,
)
from backend.services.hospitals import ACTIVE_FACILITIES
from datetime import datetime


# ── Seasonal factors (from synthetic_data_creation.py) ───────────────────────
SEASONAL_FACTORS: dict[str, float] = {
    "Jan": 1.0,
    "Feb": 1.3,
    "Mar": 1.2,
    "Apr": 0.9,
}

DEPT_LAMBDAS: dict[str, float] = {
    "ER": 20.0,
    "ICU": 10.0,
    "Maternity": 5.0,
}


def _season_factor(d: date) -> float:
    month_abbr = d.strftime("%b")
    return SEASONAL_FACTORS.get(month_abbr, 1.0)


def _poisson_arrivals(lam: float) -> float:
    """Simple Poisson draw (or return expected value for deterministic mode)."""
    import math
    # For API responses we return expected values (deterministic) so the
    # dashboard shows stable numbers.  Replace with np.random.poisson(lam)
    # if you want stochastic draws.
    return round(lam, 1)


def generate_inflow_for_period(
    facility_ids: list[str],
    start: date,
    end: date,
    seasonality_factor: float = 1.0,
) -> list[FacilityDailyInflow]:
    """
    Reproduce the synthetic_data_creation.py logic for an arbitrary date range.

    DS hook: replace this entire function body with a call to
        from src.synthetic_data_creation import generate_arrivals
    """
    records = []
    current = start
    while current <= end:
        sf = _season_factor(current) * seasonality_factor
        for fid in facility_ids:
            depts = []
            total = 0.0
            for dept, lam in DEPT_LAMBDAS.items():
                arr = _poisson_arrivals(lam * sf)
                depts.append(DepartmentInflow(department=dept, arrivals=arr))
                total += arr
            records.append(FacilityDailyInflow(
                facility_id=fid,
                date=current,
                departments=depts,
                total_arrivals=round(total, 1),
            ))
        current += timedelta(days=1)
    return records


def get_inflow(req: InflowRequest) -> InflowResponse:
    """
    DS hook (Option B): load from pre-generated CSV if DS_DATA_PATH is set.
    Otherwise synthesise on the fly using the DS project logic above.
    """
    ds_data_path = os.environ.get("DS_DATA_PATH", "")
    if ds_data_path:
        csv_path = os.path.join(ds_data_path, "synthetic_hospital_arrivals.csv")
        if os.path.isfile(csv_path):
            return _load_from_csv(csv_path, req)

    # Fall back to on-the-fly generation
    start = req.start_date or date(2026, 1, 1)
    end = req.end_date or date(2026, 4, 30)

    if req.facility_id:
        facility_ids = [req.facility_id]
    else:
        facility_ids = [f.facility_code for f in ACTIVE_FACILITIES]

    records = generate_inflow_for_period(
        facility_ids, start, end, req.seasonality_factor
    )

    return InflowResponse(
        facility_id=req.facility_id,
        seasonality_factor=req.seasonality_factor,
        records=records,
        timestamp=datetime.utcnow(),
    )


# ── CSV loader for pre-generated data ────────────────────────────────────────

def _load_from_csv(csv_path: str, req: InflowRequest) -> InflowResponse:
    """Load synthetic_hospital_arrivals.csv and filter by request params."""
    from datetime import datetime as dt
    records_by_key: dict[tuple, dict] = {}

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fid = row["Facility_ID"]
            if req.facility_id and fid != req.facility_id:
                continue
            d = date.fromisoformat(row["Date"][:10])
            if req.start_date and d < req.start_date:
                continue
            if req.end_date and d > req.end_date:
                continue

            key = (fid, d)
            if key not in records_by_key:
                records_by_key[key] = {"facility_id": fid, "date": d, "depts": []}
            arr = float(row["Predicted_Arrivals"]) * req.seasonality_factor
            records_by_key[key]["depts"].append(
                DepartmentInflow(department=row["Departments"], arrivals=round(arr, 1))
            )

    records = [
        FacilityDailyInflow(
            facility_id=v["facility_id"],
            date=v["date"],
            departments=v["depts"],
            total_arrivals=round(sum(d.arrivals for d in v["depts"]), 1),
        )
        for v in records_by_key.values()
    ]
    records.sort(key=lambda r: (r.facility_id, r.date))

    return InflowResponse(
        facility_id=req.facility_id,
        seasonality_factor=req.seasonality_factor,
        records=records,
        timestamp=dt.utcnow(),
    )

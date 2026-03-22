"""
optimizer.py — Exact port of the three PuLP optimisation functions
from 04_Optimization.ipynb.

Functions ported (unchanged logic):
  facility_optimization(demand_dict, beds_dict)
  parish_optimization(demand_dict, beds_dict, df)
  system_optimization(demand_dict, beds_dict, df, reserve=0.10)

The scenario demand multipliers from the notebook are also preserved:
  Normal     : 1.0 ×  yhat
  Outbreak   : 1.3 ×  yhat
  Disaster   : 1.5 ×  yhat
  FluSeason  : 1.1 ×  yhat

HOW TO CONNECT YOUR DS CODE:
  Once your Prophet forecasts are producing real yhat values, plug them in
  by calling run_forecast() from services/forecaster.py (already wired below).
  The optimisation functions themselves are already an exact copy — no changes
  needed there.
"""

from __future__ import annotations
import os
from datetime import datetime
import pandas as pd

from backend.models.schemas import (
    OptimiseRequest, OptimiseResponse, AllocationResult,
)
from backend.services.forecaster import run_forecast
from backend.services.hospitals import ACTIVE_FACILITIES, FACILITY_MAP
from backend.models.schemas import ForecastRequest


# ── Scenario multipliers (from 04_Optimization.ipynb) ────────────────────────
SCENARIO_MULTIPLIERS: dict[str, float] = {
    "Normal":    1.0,
    "Outbreak":  1.3,
    "Disaster":  1.5,
    "FluSeason": 1.1,
}


# ── Exact copies of the three PuLP functions from the notebook ────────────────

def facility_optimization(demand_dict: dict, beds_dict: dict) -> pd.DataFrame:
    import pulp
    prob = pulp.LpProblem("Facility_Optimization", pulp.LpMinimize)
    x = pulp.LpVariable.dicts("assign", demand_dict.keys(), lowBound=0)

    prob += pulp.lpSum((demand_dict[f] - x[f]) for f in demand_dict.keys())

    for f in demand_dict.keys():
        prob += x[f] <= beds_dict[f]
        prob += x[f] <= demand_dict[f]

    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    return pd.DataFrame([
        {
            "Facility_ID": f,
            "Demand":      demand_dict[f],
            "Beds":        beds_dict[f],
            "Assigned":    x[f].varValue,
            "Overflow":    max(0, demand_dict[f] - x[f].varValue),
        }
        for f in demand_dict.keys()
    ])


def parish_optimization(
    demand_dict: dict,
    beds_dict: dict,
    df: pd.DataFrame,
) -> pd.DataFrame:
    import pulp
    parish_capacity = df.groupby("Parish")["Beds"].sum().to_dict()
    parish_demand = {
        p: sum(demand_dict[f] for f in df[df["Parish"] == p]["Facility_ID"])
        for p in parish_capacity.keys()
    }

    prob = pulp.LpProblem("Parish_Optimization", pulp.LpMinimize)
    x = pulp.LpVariable.dicts("assign", demand_dict.keys(), lowBound=0)

    prob += pulp.lpSum((demand_dict[f] - x[f]) for f in demand_dict.keys())

    for f in demand_dict.keys():
        prob += x[f] <= beds_dict[f]

    for parish in parish_capacity.keys():
        parish_facilities = df[df["Parish"] == parish]["Facility_ID"]
        prob += pulp.lpSum(x[f] for f in parish_facilities) <= parish_capacity[parish]
        prob += pulp.lpSum(x[f] for f in parish_facilities) <= parish_demand[parish]

    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    return pd.DataFrame([
        {
            "Facility_ID": f,
            "Parish":      df.loc[df["Facility_ID"] == f, "Parish"].values[0],
            "Demand":      demand_dict[f],
            "Beds":        beds_dict[f],
            "Assigned":    x[f].varValue,
            "Overflow":    max(0, demand_dict[f] - x[f].varValue),
        }
        for f in demand_dict.keys()
    ])


def system_optimization(
    demand_dict: dict,
    beds_dict: dict,
    df: pd.DataFrame,
    reserve: float = 0.10,
) -> pd.DataFrame:
    import pulp
    system_capacity = df["Beds"].sum()
    system_demand = sum(demand_dict.values())

    prob = pulp.LpProblem("System_Optimization", pulp.LpMinimize)
    x = pulp.LpVariable.dicts("assign", demand_dict.keys(), lowBound=0)

    prob += pulp.lpSum((demand_dict[f] - x[f]) for f in demand_dict.keys())

    for f in demand_dict.keys():
        prob += x[f] <= beds_dict[f]

    # 10 % reserve (or custom value) matches notebook
    prob += pulp.lpSum(x[f] for f in demand_dict.keys()) <= system_capacity * (1 - reserve)
    prob += pulp.lpSum(x[f] for f in demand_dict.keys()) <= system_demand

    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    return pd.DataFrame([
        {
            "Facility_ID": f,
            "Demand":      demand_dict[f],
            "Beds":        beds_dict[f],
            "Assigned":    x[f].varValue,
            "Overflow":    max(0, demand_dict[f] - x[f].varValue),
        }
        for f in demand_dict.keys()
    ])


# ── API entry point ───────────────────────────────────────────────────────────

def run_optimisation(req: OptimiseRequest) -> OptimiseResponse:
    try:
        import pulp
    except ImportError:
        raise RuntimeError("PuLP is not installed. Run: pip install pulp")

    # 1. Get base yhat forecasts
    forecast_resp = run_forecast(ForecastRequest(facility_id=None, seasonality_factor=1.0))

    # 2. Build the forecast_test_df structure used in the notebook
    rows = []
    for fp in forecast_resp.forecasts:
        fac = FACILITY_MAP.get(fp.facility_id)
        if fac is None:
            continue
        rows.append({
            "Facility_ID": fp.facility_id,
            "Beds":        fp.beds,
            "Parish":      fp.parish,
            "yhat":        fp.yhat,
        })
    forecast_test_df = pd.DataFrame(rows)

    if forecast_test_df.empty:
        return OptimiseResponse(
            status="Error",
            solver_message="No forecast data available",
            scenario=req.scenario,
            layer=req.layer,
            allocations=[],
            total_overflow=0.0,
            timestamp=datetime.utcnow(),
        )

    # 3. Build demand dict using scenario multiplier (notebook pattern)
    base_demand = dict(zip(forecast_test_df["Facility_ID"], forecast_test_df["yhat"]))
    mult = SCENARIO_MULTIPLIERS.get(req.scenario, 1.0)
    demand_dict = {f: int(d * mult) for f, d in base_demand.items()}
    beds_dict = dict(zip(forecast_test_df["Facility_ID"], forecast_test_df["Beds"]))

    # 4. Run the selected optimisation layer (exact notebook functions)
    try:
        if req.layer == "Facility":
            result_df = facility_optimization(demand_dict, beds_dict)
        elif req.layer == "Parish":
            result_df = parish_optimization(demand_dict, beds_dict, forecast_test_df)
        else:  # System
            result_df = system_optimization(
                demand_dict, beds_dict, forecast_test_df, reserve=req.system_reserve
            )
    except Exception as exc:
        return OptimiseResponse(
            status="Error",
            solver_message=str(exc),
            scenario=req.scenario,
            layer=req.layer,
            allocations=[],
            total_overflow=0.0,
            timestamp=datetime.utcnow(),
        )

    # 5. Map DataFrame rows → AllocationResult schema
    allocations = []
    for _, row in result_df.iterrows():
        fid = row["Facility_ID"]
        fac = FACILITY_MAP.get(fid)
        allocations.append(AllocationResult(
            facility_id=fid,
            name=fac.name if fac else None,
            parish=row.get("Parish", fac.parish if fac else None),
            demand=float(row["Demand"]),
            beds=int(row["Beds"]),
            assigned=float(row["Assigned"]) if row["Assigned"] is not None else 0.0,
            overflow=float(row["Overflow"]),
            scenario=req.scenario,
            layer=req.layer,
        ))

    total_overflow = round(sum(a.overflow for a in allocations), 1)

    return OptimiseResponse(
        status="Optimal",
        solver_message=f"PuLP CBC — {req.layer} layer, {req.scenario} scenario",
        scenario=req.scenario,
        layer=req.layer,
        allocations=allocations,
        total_overflow=total_overflow,
        timestamp=datetime.utcnow(),
    )

"""
models/schemas.py — Pydantic v2 models for the JamaicaHealthOps API.
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── Facilities ────────────────────────────────────────────────────────────────

class FacilityInfo(BaseModel):
    facility_code: str
    name: str
    parish: str
    health_region: str
    facility_type: str
    ownership: str
    status: str
    beds_z990: int
    beds_z996: int
    beds_z999: int


# ── Beds ──────────────────────────────────────────────────────────────────────

class FacilityBedStatus(BaseModel):
    facility_code: str
    name: str
    parish: str
    health_region: str
    total_beds: int
    occupied_beds: int
    available_beds: int
    utilization_pct: float
    rag_status: str          # "stable" | "warning" | "critical"
    last_updated: datetime


class BedsResponse(BaseModel):
    facilities: list[FacilityBedStatus]
    total_beds: int
    total_occupied: int
    total_available: int
    system_utilization_pct: float
    critical_count: int
    timestamp: datetime


# ── Inflow ────────────────────────────────────────────────────────────────────

class DepartmentInflow(BaseModel):
    department: str          # "ER" | "ICU" | "Maternity"
    arrivals: float


class FacilityDailyInflow(BaseModel):
    facility_id: str
    date: date
    departments: list[DepartmentInflow]
    total_arrivals: float


class InflowRequest(BaseModel):
    facility_id: Optional[str] = None
    seasonality_factor: float = Field(1.0, ge=0.5, le=2.0)
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class InflowResponse(BaseModel):
    facility_id: Optional[str]
    seasonality_factor: float
    records: list[FacilityDailyInflow]
    timestamp: datetime


# ── Forecast ──────────────────────────────────────────────────────────────────

class ForecastPoint(BaseModel):
    facility_id: str
    name: str
    parish: str
    beds: int
    yhat: float
    yhat_lower: Optional[float] = None
    yhat_upper: Optional[float] = None


class ForecastRequest(BaseModel):
    facility_id: Optional[str] = None
    seasonality_factor: float = Field(1.0, ge=0.5, le=2.0)


class ForecastResponse(BaseModel):
    forecasts: list[ForecastPoint]
    timestamp: datetime


# ── Optimisation ──────────────────────────────────────────────────────────────

class AllocationResult(BaseModel):
    facility_id: str
    name: Optional[str] = None
    parish: Optional[str] = None
    demand: float
    beds: int
    assigned: float
    overflow: float
    scenario: str
    layer: str


class OptimiseRequest(BaseModel):
    scenario: str = Field("Normal", description="Normal | Outbreak | Disaster | FluSeason")
    layer: str    = Field("System", description="Facility | Parish | System")
    system_reserve: float = Field(0.10, ge=0.0, le=0.5, description="System reserve fraction")


class OptimiseResponse(BaseModel):
    status: str
    solver_message: str
    scenario: str
    layer: str
    allocations: list[AllocationResult]
    total_overflow: float
    timestamp: datetime

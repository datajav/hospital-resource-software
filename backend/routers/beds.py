"""GET /api/beds — live bed counts for all facilities."""

import random
from datetime import datetime
from fastapi import APIRouter
from backend.models.schemas import BedsResponse, FacilityBedStatus
from backend.services.hospitals import ACTIVE_FACILITIES

router = APIRouter(prefix="/api/beds", tags=["Beds"])

# Simulated occupancy — replace with a real census feed / DB read in production
_occupancy: dict[str, int] = {
    f.facility_code: int(f.beds_z999 * 0.78)
    for f in ACTIVE_FACILITIES
}


def _rag(util: float) -> str:
    return "critical" if util >= 0.92 else "warning" if util >= 0.80 else "stable"


@router.get("", response_model=BedsResponse, summary="Live bed counts for all facilities")
def get_beds():
    """
    Returns current bed occupancy for every facility with a Z999 bed count.

    DS hook: replace _occupancy[code] lookups with a read from
    data/merged_facility_data.csv or a live database query.
    """
    facilities = []
    for fac in ACTIVE_FACILITIES:
        occ = _occupancy[fac.facility_code]
        util = occ / fac.beds_z999 if fac.beds_z999 > 0 else 0.0
        facilities.append(FacilityBedStatus(
            facility_code=fac.facility_code,
            name=fac.name,
            parish=fac.parish,
            health_region=fac.health_region,
            total_beds=fac.beds_z999,
            occupied_beds=occ,
            available_beds=fac.beds_z999 - occ,
            utilization_pct=round(util, 4),
            rag_status=_rag(util),
            last_updated=datetime.utcnow(),
        ))

    total_occ = sum(f.occupied_beds for f in facilities)
    total_beds = sum(f.total_beds for f in facilities)

    return BedsResponse(
        facilities=facilities,
        total_beds=total_beds,
        total_occupied=total_occ,
        total_available=total_beds - total_occ,
        system_utilization_pct=round(total_occ / total_beds, 4) if total_beds else 0.0,
        critical_count=sum(1 for f in facilities if f.rag_status == "critical"),
        timestamp=datetime.utcnow(),
    )


@router.post("/simulate-tick", summary="[Dev] Advance occupancy by one random tick")
def simulate_tick():
    """
    Simulate a live census update.  Useful during development before
    a real data feed is connected.  Remove / gate behind an env flag
    before deploying to production.
    """
    for fac in ACTIVE_FACILITIES:
        delta = random.randint(-4, 5)
        _occupancy[fac.facility_code] = max(
            0, min(fac.beds_z999, _occupancy[fac.facility_code] + delta)
        )
    return {"message": "Tick applied", "occupancy": dict(_occupancy)}

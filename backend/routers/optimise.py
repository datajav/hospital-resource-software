"""POST /api/optimise — PuLP bed allocation solver."""

from fastapi import APIRouter, HTTPException
from backend.models.schemas import OptimiseRequest, OptimiseResponse
from backend.services.optimizer import run_optimisation

router = APIRouter(prefix="/api/optimise", tags=["Optimisation"])


@router.post("", response_model=OptimiseResponse, summary="Run PuLP bed allocation")
def optimise(req: OptimiseRequest):
    """
    Runs the facility / parish / system PuLP optimisation from
    04_Optimization.ipynb for the requested scenario and layer.

    Scenarios : Normal | Outbreak | Disaster | FluSeason
    Layers    : Facility | Parish | System

    DS hook: services/optimizer.py contains the exact notebook functions.
    """
    try:
        result = run_optimisation(req)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if result.status == "Error":
        raise HTTPException(status_code=422, detail=result.solver_message)

    return result

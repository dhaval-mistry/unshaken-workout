"""Unauthenticated process and dependency health endpoints."""

from typing import Literal

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    """Stable response schema for liveness and readiness probes."""

    status: Literal["ok"]


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    """Report that the API process can accept requests without probing dependencies."""

    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
async def readiness(request: Request) -> HealthResponse | JSONResponse:
    """Report ready only after the database accepts a minimal query."""

    database = request.app.state.database
    if await database.check_connection():
        return HealthResponse(status="ok")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"status": "unavailable"}
    )

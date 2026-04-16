from fastapi import APIRouter, HTTPException

from simphonia.core import BusNotFound, CommandNotFound, DispatchError, default_registry
from simphonia.http.schemas import (
    BusDTO,
    CommandDTO,
    DispatchRequest,
    DispatchResponse,
)

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/bus", response_model=list[BusDTO])
def list_buses() -> list[BusDTO]:
    buses = default_registry().all()
    return [BusDTO(name=name, command_count=len(bus.list())) for name, bus in buses.items()]


@router.get("/bus/{bus_name}/commands", response_model=list[CommandDTO])
def list_commands(bus_name: str) -> list[CommandDTO]:
    try:
        bus = default_registry().get(bus_name)
    except BusNotFound as exc:
        raise HTTPException(status_code=404, detail=_error("BusNotFound", str(exc))) from exc
    return [CommandDTO(code=c.code, description=c.description) for c in bus.list()]


@router.post("/bus/{bus_name}/dispatch", response_model=DispatchResponse)
def dispatch(bus_name: str, req: DispatchRequest) -> DispatchResponse:
    try:
        bus = default_registry().get(bus_name)
    except BusNotFound as exc:
        raise HTTPException(status_code=404, detail=_error("BusNotFound", str(exc))) from exc

    try:
        result = bus.dispatch(req.code, req.payload)
    except CommandNotFound as exc:
        raise HTTPException(status_code=404, detail=_error("CommandNotFound", str(exc))) from exc
    except DispatchError as exc:
        raise HTTPException(status_code=500, detail=_error("DispatchError", str(exc))) from exc

    return DispatchResponse(result=result)


def _error(type_: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"type": type_, "message": message}}

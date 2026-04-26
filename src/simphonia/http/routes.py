from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from simphonia.core import BusNotFound, CommandNotFound, DispatchError, default_registry
from simphonia.http import sse
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


@router.get("/bus/activity/stream/{session_id}")
async def stream_activity_events(session_id: str) -> StreamingResponse:
    return StreamingResponse(
        sse.subscribe(session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/bus/chat/stream/{session_id}")
async def stream_chat_events(session_id: str) -> StreamingResponse:
    return StreamingResponse(
        sse.subscribe(session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/bus/photo/stream/{session_id}")
async def stream_photo_events(session_id: str) -> StreamingResponse:
    """SSE des événements `photo.published` pour la session courante.

    Le listener `sse._photo_publish_to_sse` (branché au boot) capture les
    `dispatch("publish")` du bus `photo` et les route ici par `session_id`.
    Le client simweb reçoit `{type: "photo.published", photo_id, from_char,
    photo_type, url}` quand une photo qu'il a déclenchée est prête.
    """
    return StreamingResponse(
        sse.subscribe(session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/photos/{photo_id}")
def serve_photo(photo_id: str) -> FileResponse:
    """Sert le binaire PNG d'une photo générée.

    Sécurité v1 : aucune ACL — tout client connaissant le `photo_id`
    (UUID v4) peut récupérer le fichier. C'est acceptable v1 vu que
    le `photo_id` n'est exposé que via le SSE de la session émettrice.
    L'ACL `from_char` matchant la session courante sera ajoutée ultérieurement
    si nécessaire (cf. `documents/photo_service.md` § 7).
    """
    from simphonia.services import photo_service
    try:
        doc = photo_service.get().get_photo(photo_id)
    except RuntimeError as exc:
        # photo_service pas configuré (pas de Mongo) → 503
        raise HTTPException(status_code=503, detail=_error("ServiceUnavailable", str(exc))) from exc
    if doc is None:
        raise HTTPException(status_code=404, detail=_error("PhotoNotFound", f"photo_id={photo_id}"))
    if doc.get("status") != "completed":
        raise HTTPException(
            status_code=409,
            detail=_error(
                "PhotoNotReady",
                f"photo_id={photo_id} status={doc.get('status')}",
            ),
        )
    file_path = doc.get("file_path")
    if not file_path or not Path(file_path).exists():
        raise HTTPException(
            status_code=410,
            detail=_error("PhotoFileMissing", f"file_path={file_path}"),
        )
    return FileResponse(path=file_path, media_type="image/png", filename=f"{photo_id}.png")


def _error(type_: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"type": type_, "message": message}}

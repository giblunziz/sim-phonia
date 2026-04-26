"""Publisher SSE thread-safe : permet aux commandes (threads sync) de pousser des événements
vers les clients HTTP abonnés (boucle asyncio).
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

_session_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)
_loop: asyncio.AbstractEventLoop | None = None

_KEEPALIVE_TIMEOUT = 25  # secondes


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def publish(session_id: str, event: dict[str, Any]) -> None:
    """Appelable depuis n'importe quel thread — pousse l'événement vers les abonnés SSE."""
    if _loop is None:
        return
    for q in list(_session_queues.get(session_id, [])):
        asyncio.run_coroutine_threadsafe(q.put(event), _loop)


async def subscribe(session_id: str):
    """Générateur async — yield des lignes SSE (data: ...\n\n)."""
    q: asyncio.Queue[dict | None] = asyncio.Queue()
    _session_queues[session_id].append(q)
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=_KEEPALIVE_TIMEOUT)
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                yield 'data: {"type":"keepalive"}\n\n'
    finally:
        try:
            _session_queues[session_id].remove(q)
        except ValueError:
            pass


def close_session(session_id: str) -> None:
    """Envoie le sentinel None à tous les abonnés de la session (déclenchée par chat.stop)."""
    publish(session_id, None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
#  Bridges bus → SSE
# ---------------------------------------------------------------------------

def _photo_publish_to_sse(payload: dict[str, Any]) -> None:
    """Listener du bus `photo` → push SSE quand une photo est publiée.

    Filtre : ne pousse que les payloads de l'événement `publish`, caractérisés
    par la présence de la clé `url`. Les payloads de `take_shoot` /
    `take_selfy` (qui contiennent `markdown`, pas `url`) sont ignorés.

    Routage SSE par `session_id` — chaque client simweb abonné via
    `/bus/photo/stream/{session_id}` reçoit uniquement les photos de sa
    session.
    """
    if "url" not in payload:
        return  # pas un publish event
    session_id = payload.get("session_id")
    if not session_id:
        return  # pas de routage SSE possible
    publish(session_id, {
        "type": "photo.published",
        "photo_id": payload.get("photo_id"),
        "from_char": payload.get("from_char"),
        "photo_type": payload.get("type"),
        "url": payload.get("url"),
    })


def subscribe_photo_publish_to_sse() -> None:
    """Branche le listener `_photo_publish_to_sse` sur le bus `photo`.

    À appeler une fois au boot, après que le bus `photo` ait été créé par
    le discovery (i.e. après `discover('simphonia.commands')`).
    """
    from simphonia.core import default_registry
    default_registry().get("photo").subscribe(_photo_publish_to_sse)

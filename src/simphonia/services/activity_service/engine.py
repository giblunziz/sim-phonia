"""Orchestrateur de session d'activité — pilotage MJ tour par tour."""
from __future__ import annotations

import copy
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from simphonia.core.errors import InstanceNotFound, SessionNotFound
from simphonia.services.activity_service.context_builder import (
    PRIVATE_FIELDS,
    PUBLIC_FIELDS,
    build_messages,
    build_system_prompt,
    get_tools,
)
from simphonia.services.mj_service import MJService, build_mj_service
from simphonia.utils.parser import parse_llm_json

log = logging.getLogger("simphonia.activity.engine")

MAX_RETRIES = 3


class RunState(StrEnum):
    """État du run d'activité — persisté dans Mongo, envoyé en SSE, comparé côté simweb.

    `StrEnum` : chaque membre est aussi une `str`, donc sérialisation JSON/BSON
    transparente et comparaison directe avec les strings reçues de l'extérieur.
    """
    RUNNING = "running"
    ENDED   = "ended"


# Retour ponctuel de `give_turn` (pattern async — résultat via SSE).
TURN_STATUS_PENDING = "pending"

# Champs retenus dans public / private (exclut les alias d'identification)
_PUBLIC_KEYS  = PUBLIC_FIELDS  - {"from", "message", "action"}
_PRIVATE_KEYS = PRIVATE_FIELDS


@dataclass
class SessionState:
    session_id:       str
    instance_id:      str
    run_id:           str                    # _id dans activity_runs (instance_id_YYMMDD_HHMM)
    instance:         dict                   # snapshot du run, muté en live
    activity:         dict                   # template d'activité
    scene:            dict
    characters:       dict[str, dict]        # slug → fiche personnage
    knowledge:        dict[str, list[dict]]  # slug → knowledge_entries
    system_schemas:   list[dict]             # schemas résolus depuis activity.system[enabled]
    provider_name:    str
    mj_service:       MJService | None = None  # stratégie MJ, instanciée à run/resume selon instance.mj_mode
    round:            int = 1
    state:            RunState = RunState.RUNNING
    exchange_history: list[dict] = field(default_factory=list)
    retry_counts:     dict[tuple, int] = field(default_factory=dict)


_sessions: dict[str, SessionState] = {}


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _get_session(session_id: str) -> SessionState:
    if session_id not in _sessions:
        raise SessionNotFound(session_id)
    return _sessions[session_id]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_round_event(instance: dict, round_num: int) -> dict | None:
    for event in instance.get("events", []):
        try:
            if int(event.get("round", -1)) == round_num:
                return event
        except (TypeError, ValueError):
            pass
    return None


def _resolve_whisper(instance: dict, round_num: int, target: str, position: int) -> str | None:
    for instr in instance.get("instructions", []):
        try:
            if int(instr.get("round", -1)) != round_num:
                continue
        except (TypeError, ValueError):
            continue
        who = instr.get("who")
        if who == target or str(who) == str(position):
            return instr.get("content") or instr.get("instruction")
    return None


def _make_tool_executor(from_char: str):
    def execute(name: str, args: dict) -> str:
        if name == "recall":
            from simphonia.services import character_service, memory_service
            about_raw = args.get("about", "").strip()
            about_slug = character_service.get().get_identifier(about_raw) or about_raw.lower()
            context = args.get("context", "").strip()
            memories = memory_service.get().recall(
                from_char=from_char,
                context=context,
                about=about_slug or None,
            )
            if not memories:
                return f"Je n'ai aucun souvenir de {about_raw or 'cette personne'}."
            lines = [f"# Vos souvenirs à propos de {about_raw}"]
            for m in memories:
                lines.append(f"- {m.get('value', '')}")
            return "\n".join(lines)
        return f"Outil inconnu : {name}"
    return execute


def _persist(session: SessionState) -> None:
    try:
        from simphonia.services import activity_storage
        activity_storage.get().put_run(session.run_id, session.instance)
    except Exception as exc:
        log.warning("[persist] échec upsert run %r : %s", session.run_id, exc)


def _publish_sse(session_id: str, event: dict) -> None:
    try:
        from simphonia.http import sse
        sse.publish(session_id, event)
    except Exception as exc:
        log.warning("[sse] publish échoué : %s", exc)


def _notify_mj_turn_complete(session: SessionState, exchange: dict) -> None:
    """Best-effort — un hook MJ qui plante ne doit pas bloquer le flux du run."""
    if session.mj_service is None:
        return
    try:
        session.mj_service.on_turn_complete(session, exchange)
    except Exception as exc:
        log.warning("[mj] on_turn_complete a échoué : %s", exc, exc_info=True)


def _notify_mj_session_end(session: SessionState) -> None:
    """Best-effort — idem que _notify_mj_turn_complete."""
    if session.mj_service is None:
        return
    try:
        session.mj_service.on_session_end(session)
    except Exception as exc:
        log.warning("[mj] on_session_end a échoué : %s", exc, exc_info=True)


def _build_exchange(round_num: int, speaker: str, raw_response: str, parsed: dict | None) -> dict:
    if parsed is None:
        parsed = {}
    public  = {k: v for k in _PUBLIC_KEYS  if (v := parsed.get(k))}
    private = {k: v for k in _PRIVATE_KEYS if (v := parsed.get(k))}
    return {
        "from":         speaker,
        "round":        round_num,
        "ts":           _now_iso(),
        "raw_response": raw_response,
        "public":       public,
        "private":      private,
    }


# ---------------------------------------------------------------------------
# Pipeline give_turn (exécuté en thread)
# ---------------------------------------------------------------------------

def _run_turn(session_id: str, target: str, instruction: str | None) -> None:
    try:
        _do_give_turn(session_id, target, instruction)
    except SessionNotFound:
        log.warning("[give_turn] session %r introuvable dans le thread", session_id)
    except Exception as exc:
        log.error("[give_turn] exception non gérée pour %r : %s", target, exc, exc_info=True)
        _publish_sse(session_id, {
            "type":       "activity.turn_skipped",
            "session_id": session_id,
            "speaker":    target,
            "reason":     "internal_error",
        })


def _do_give_turn(session_id: str, target: str, instruction: str | None) -> None:
    from simphonia.services import character_service, provider_registry

    session  = _get_session(session_id)
    char_svc = character_service.get()
    slug     = char_svc.get_identifier(target) or target
    retry_key = (session.round, slug)

    # Récupération position 1-based pour résolution whisper
    players  = session.instance.get("players", [])
    position = (players.index(slug) + 1) if slug in players else 0

    character        = session.characters.get(slug, {})
    knowledge_entries = session.knowledge.get(slug, [])
    round_event      = _resolve_round_event(session.instance, session.round)
    whisper          = _resolve_whisper(session.instance, session.round, slug, position)
    mj_instruction   = {"instruction": instruction} if instruction else None

    log.info("[give_turn] %r round=%d whisper=%r mj_instruction=%r",
             slug, session.round, whisper, instruction)

    # Persistance de l'instruction MJ dans instance.mj[]
    if instruction:
        session.instance.setdefault("mj", []).append({
            "round":       session.round,
            "target":      slug,
            "instruction": instruction,
            "ts":          _now_iso(),
        })

    system_prompt = build_system_prompt(
        slug, session.instance, session.activity, session.scene,
        character, knowledge_entries,
        system_schemas=session.system_schemas,
    )
    # log.info("[give_turn] system_prompt %r:\n%s", slug, system_prompt)

    messages = build_messages(
        slug, session.instance, session.exchange_history,
        current_round_event=round_event,
        whisper=whisper,
        mj_instruction=mj_instruction,
        amorce=None,
    )
    has_schema = bool(session.system_schemas)
    if not messages:
        trigger = "C'est ton tour de prendre la parole."
        if has_schema:
            trigger += " Rappel : ta réponse doit être UNIQUEMENT du JSON valide, sans texte avant ni après."
        messages = [{"role": "user", "content": trigger}]

    tools    = get_tools(session.activity)
    provider = provider_registry.get(session.provider_name)
    executor = _make_tool_executor(slug)

    # Circuit breaker
    while True:
        raw_response: str | None = None
        parsed: dict | None      = None
        try:
            raw_response, _ = provider.call(
                system_prompt, messages,
                temperature=session.instance.get("temperature"),
                tools=tools,
                tool_executor=executor,
            )
            log.info("[raw_response]  %r:\n%s", slug, raw_response)

            if raw_response:
                parsed = parse_llm_json(raw_response)
        except Exception as exc:
            log.warning("[give_turn] provider error pour %r : %s", slug, exc)

        log.info("[give_turn] raw %r:\n%s", slug, raw_response or "<vide>")

        if parsed is not None:
            break

        session.retry_counts[retry_key] = session.retry_counts.get(retry_key, 0) + 1
        attempts = session.retry_counts[retry_key]
        log.warning("[give_turn] parse KO pour %r (%d/%d)", slug, attempts, MAX_RETRIES)
        if attempts >= MAX_RETRIES:
            log.error("[give_turn] skip %r après %d tentatives", slug, MAX_RETRIES)
            _publish_sse(session_id, {
                "type":       "activity.turn_skipped",
                "session_id": session_id,
                "speaker":    slug,
                "reason":     "parse_error",
            })
            return

    exchange = _build_exchange(session.round, slug, raw_response or "", parsed)
    session.exchange_history.append(exchange)
    session.instance.setdefault("exchanges", []).append(exchange)
    _persist(session)

    log.info("[give_turn] %r round=%d — public=%s", slug, session.round, exchange["public"])

    _publish_sse(session_id, {
        "type":       "activity.turn_complete",
        "session_id": session_id,
        "speaker":    slug,
        "round":      session.round,
        "public":     exchange["public"],
        "private":    exchange["private"],
        "whisper":    whisper,
    })

    _notify_mj_turn_complete(session, exchange)


# ---------------------------------------------------------------------------
# API publique — appelée par les commandes bus
# ---------------------------------------------------------------------------

def run(instance_id: str) -> dict:
    from simphonia.services import (
        activity_storage, character_service, character_storage, provider_registry,
    )

    svc_instance = activity_storage.get().get_instance(instance_id)
    if svc_instance is None:
        raise InstanceNotFound(instance_id)

    activity_slug = svc_instance.get("activity") or svc_instance.get("activity_id", "")
    scene_slug    = svc_instance.get("scene", "")
    providers     = svc_instance.get("providers") or {}
    if isinstance(providers, dict):
        provider_name = providers.get("players") or providers.get("mj") or provider_registry.list_names()[0]
    elif isinstance(providers, list) and providers:
        provider_name = providers[0]
    else:
        provider_name = provider_registry.list_names()[0]

    activity = activity_storage.get().get_activity(activity_slug) or {}
    scene    = (activity_storage.get().get_scene(scene_slug) or {}) if scene_slug else {}

    # Résolution des schemas system activés (une fois pour toute la session)
    system_schemas: list[dict] = []
    for entry in activity.get("system", []):
        if entry.get("enabled"):
            slug = entry.get("schema", "")
            if slug:
                schema_doc = activity_storage.get().get_schema(slug)
                if schema_doc:
                    system_schemas.append(schema_doc)
                else:
                    log.warning("[run] schema %r introuvable pour l'activité %r", slug, activity_slug)

    char_svc = character_service.get()
    players  = svc_instance.get("players", [])

    characters: dict[str, dict] = {}
    knowledge:  dict[str, list[dict]] = {}
    for player in players:
        try:
            characters[player] = char_svc.get_character(player)
        except Exception as exc:
            log.warning("[run] fiche introuvable pour %r : %s", player, exc)
            characters[player] = {}

        others = [p for p in players if p != player]
        if others:
            try:
                knowledge[player] = character_storage.get().list_knowledge(filter={
                    "from":     player,
                    "about":    {"$in": others},
                    "activity": "presentation",
                })
            except Exception as exc:
                log.warning("[run] knowledge introuvable pour %r : %s", player, exc)
                knowledge[player] = []
        else:
            knowledge[player] = []

    session_id = str(uuid.uuid4())
    run_id     = f"{instance_id}_{datetime.now(timezone.utc).strftime('%y%m%d_%H%M')}"

    # Snapshot autonome — activity_instances reste intact
    run_data = copy.deepcopy(svc_instance)
    run_data.pop("_id", None)
    run_data.update({
        "instance_id":   instance_id,
        "state":         RunState.RUNNING,
        "current_round": 1,
        "ts_started":    _now_iso(),
        "exchanges":     [],
        "mj":            [],
    })

    mj_mode = svc_instance.get("mj_mode", "human")

    session = SessionState(
        session_id=session_id,
        instance_id=instance_id,
        run_id=run_id,
        instance=run_data,
        activity=activity,
        scene=scene,
        characters=characters,
        knowledge=knowledge,
        system_schemas=system_schemas,
        provider_name=provider_name,
        mj_service=build_mj_service(mj_mode),
    )
    _sessions[session_id] = session
    _persist(session)

    event = _resolve_round_event(svc_instance, 1)
    payload = {
        "session_id": session_id,
        "players":    players,
        "round":      1,
        "starter":    svc_instance.get("starter"),
        "amorce":     svc_instance.get("amorce"),
        "event":      event,
        "mj_mode":    mj_mode,
    }
    _publish_sse(session_id, {"type": "activity.started", **payload})
    log.info("[run] session=%s instance=%r players=%s mj_mode=%s",
             session_id, instance_id, players, mj_mode)
    return payload


def resume(run_id: str) -> dict:
    """Reconstruit un SessionState depuis un activity_run MongoDB existant."""
    from simphonia.services import (
        activity_storage, character_service, character_storage, provider_registry,
    )

    run_doc = activity_storage.get().get_run(run_id)
    if run_doc is None:
        raise InstanceNotFound(run_id)

    instance_id   = run_doc.get("instance_id", run_id)
    activity_slug = run_doc.get("activity") or ""
    scene_slug    = run_doc.get("scene", "")
    providers     = run_doc.get("providers") or {}
    if isinstance(providers, dict):
        provider_name = providers.get("players") or providers.get("mj") or provider_registry.list_names()[0]
    elif isinstance(providers, list) and providers:
        provider_name = providers[0]
    else:
        provider_name = provider_registry.list_names()[0]

    activity = activity_storage.get().get_activity(activity_slug) or {}
    scene    = (activity_storage.get().get_scene(scene_slug) or {}) if scene_slug else {}

    system_schemas: list[dict] = []
    for entry in activity.get("system", []):
        if entry.get("enabled"):
            slug = entry.get("schema", "")
            if slug:
                schema_doc = activity_storage.get().get_schema(slug)
                if schema_doc:
                    system_schemas.append(schema_doc)

    char_svc = character_service.get()
    players  = run_doc.get("players", [])

    characters: dict[str, dict] = {}
    knowledge:  dict[str, list[dict]] = {}
    for player in players:
        try:
            characters[player] = char_svc.get_character(player)
        except Exception as exc:
            log.warning("[resume] fiche introuvable pour %r : %s", player, exc)
            characters[player] = {}
        others = [p for p in players if p != player]
        if others:
            try:
                knowledge[player] = character_storage.get().list_knowledge(filter={
                    "from":     player,
                    "about":    {"$in": others},
                    "activity": "presentation",
                })
            except Exception as exc:
                log.warning("[resume] knowledge introuvable pour %r : %s", player, exc)
                knowledge[player] = []
        else:
            knowledge[player] = []

    existing_exchanges = run_doc.get("exchanges", [])
    current_round      = int(run_doc.get("current_round", 1))

    session_id = str(uuid.uuid4())

    mj_mode = run_doc.get("mj_mode", "human")

    session = SessionState(
        session_id=session_id,
        instance_id=instance_id,
        run_id=run_id,
        instance=run_doc,
        activity=activity,
        scene=scene,
        characters=characters,
        knowledge=knowledge,
        system_schemas=system_schemas,
        provider_name=provider_name,
        mj_service=build_mj_service(mj_mode),
        round=current_round,
        state=RunState(run_doc.get("state", RunState.RUNNING)),
        exchange_history=list(existing_exchanges),
    )
    _sessions[session_id] = session

    event = _resolve_round_event(run_doc, current_round)
    payload = {
        "session_id":  session_id,
        "run_id":      run_id,
        "players":     players,
        "round":       current_round,
        "starter":     run_doc.get("starter"),
        "amorce":      run_doc.get("amorce"),
        "event":       event,
        "exchanges":   existing_exchanges,
        "max_rounds":  run_doc.get("max_rounds"),
        "state":       session.state,
    }
    _publish_sse(session_id, {"type": "activity.resumed", **payload})
    log.info("[resume] session=%s run=%r players=%s round=%d", session_id, run_id, players, current_round)
    return payload


def give_turn(session_id: str, target: str, instruction: str | None = None) -> dict:
    _get_session(session_id)  # fail-fast si session inconnue
    t = threading.Thread(
        target=_run_turn,
        args=(session_id, target, instruction),
        daemon=True,
        name=f"activity-turn-{session_id[:8]}-{target}",
    )
    t.start()
    return {"status": TURN_STATUS_PENDING, "session_id": session_id, "target": target}


def next_round(session_id: str) -> dict:
    session = _get_session(session_id)
    session.round += 1
    session.retry_counts.clear()
    session.instance["current_round"] = session.round

    max_rounds = int(session.instance.get("max_rounds", 0) or 0)
    if max_rounds and session.round > max_rounds:
        return end(session_id)

    event = _resolve_round_event(session.instance, session.round)
    _persist(session)

    payload = {"session_id": session_id, "round": session.round, "event": event, "state": session.state}
    _publish_sse(session_id, {"type": "activity.round_changed", **payload})
    log.info("[next_round] session=%s round=%d", session_id, session.round)
    return payload


def end(session_id: str) -> dict:
    session = _get_session(session_id)
    session.state = RunState.ENDED
    session.instance["state"]    = RunState.ENDED
    session.instance["ts_ended"] = _now_iso()
    _persist(session)

    _notify_mj_session_end(session)

    del _sessions[session_id]
    _publish_sse(session_id, {"type": "activity.ended", "session_id": session_id})
    log.info("[end] session=%s closed", session_id)
    return {"state": RunState.ENDED, "session_id": session_id}

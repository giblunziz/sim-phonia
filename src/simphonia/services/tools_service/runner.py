"""Moteur d'exécution `tools_service` — double boucle `sources × subjects`.

Run démarré en thread background (daemon), suivi via `get_run_status(run_id)`
pour alimenter la progress bar UI. Aucun bus applicatif, aucune SSE scénario.

Best-effort : une cellule qui plante n'arrête pas le run. Les erreurs sont
agrégées dans `state.cells[]` et dans le fichier `_run.meta.json` écrit en
fin d'exécution.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from simphonia.config import PROJECT_ROOT
from simphonia.services import activity_storage, provider_registry
from simphonia.services import tools_service
from simphonia.services.tools_service.builder import build_tools_system_prompt

log = logging.getLogger("simphonia.tools")


@dataclass
class RunState:
    run_id: str
    task_slug: str
    prompt: str
    temperature: float
    source_collection: str
    source_ids: list[str]
    subject_collection: str | None
    subject_ids: list[str]
    schema_id: str | None
    skip_self: bool
    model_name: str
    max_retries: int
    output_dir: Path
    status: str = "running"                   # running | completed | failed | cancelled
    cancel_requested: bool = False
    total: int = 0
    completed: int = 0
    succeeded: int = 0
    failed: int = 0
    cells: list[dict] = field(default_factory=list)
    started_at: str = ""
    ended_at: str | None = None
    error: str | None = None


_runs: dict[str, RunState] = {}
_runs_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────
# API publique — appelée par la commande bus `tools/run` et `tools/status`
# ─────────────────────────────────────────────────────────────────────

def start_run(
    *,
    task_slug: str,
    prompt: str,
    temperature: float,
    source_collection: str,
    source_ids: list[str],
    subject_collection: str | None,
    subject_ids: list[str] | None,
    schema_id: str | None,
    skip_self: bool,
    model_name: str,
    output_dir_root: str = "output",
    max_retries: int = 3,
) -> str:
    """Démarre un run dans un thread, retourne le `run_id` immédiatement."""
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d_%H%M%S")
    run_id = f"{ts}_{uuid.uuid4().hex[:6]}"
    output_dir = (PROJECT_ROOT / output_dir_root / task_slug / ts).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    subjects_list = list(subject_ids) if subject_ids else [None]
    cells = [
        (s, sb) for s in source_ids for sb in subjects_list
        if not (skip_self and sb is not None and sb == s)
    ]

    state = RunState(
        run_id=run_id,
        task_slug=task_slug,
        prompt=prompt,
        temperature=temperature,
        source_collection=source_collection,
        source_ids=list(source_ids),
        subject_collection=subject_collection,
        subject_ids=list(subject_ids or []),
        schema_id=schema_id,
        skip_self=skip_self,
        model_name=model_name,
        max_retries=max(1, int(max_retries)),
        output_dir=output_dir,
        total=len(cells),
        started_at=now.isoformat(),
    )
    with _runs_lock:
        _runs[run_id] = state

    log.info(
        "[tools.run] start run_id=%s task=%s cells=%d output=%s",
        run_id, task_slug, state.total, output_dir,
    )

    threading.Thread(
        target=_execute_run,
        args=(state, cells),
        daemon=True,
    ).start()

    return run_id


def get_run_status(run_id: str) -> dict | None:
    """Retourne l'état courant du run (dict JSON-safe) ou None si inconnu."""
    with _runs_lock:
        state = _runs.get(run_id)
    if state is None:
        return None
    return _state_to_dict(state)


def cancel_run(run_id: str) -> bool:
    """Demande l'interruption d'un run.

    L'interruption prend effet **entre deux cellules** (on ne peut pas
    interrompre un appel LLM en cours côté provider). Le run passe alors
    en status `cancelled`, écrit son `_run.meta.json` et se termine.

    Retourne `True` si la demande a été enregistrée, `False` si le run
    est inconnu ou déjà terminé.
    """
    with _runs_lock:
        state = _runs.get(run_id)
        if state is None:
            return False
        if state.status != "running":
            return False
        state.cancel_requested = True
        log.info("[tools.run] cancel demandé pour run_id=%s", run_id)
        return True


# ─────────────────────────────────────────────────────────────────────
# Exécution en thread
# ─────────────────────────────────────────────────────────────────────

def _execute_run(state: RunState, cells: list[tuple[str, str | None]]) -> None:
    try:
        svc      = tools_service.get()
        provider = provider_registry.get(state.model_name)
        schema   = _resolve_schema(state.schema_id)

        for source_id, subject_id in cells:
            with _runs_lock:
                if state.cancel_requested:
                    log.info(
                        "[tools.run] interruption run_id=%s avant cellule %s/%s",
                        state.run_id, source_id, subject_id,
                    )
                    state.status = "cancelled"
                    break
            cell = {"source": source_id, "subject": subject_id}
            try:
                source_doc = svc.get_document(state.source_collection, source_id)
                if source_doc is None:
                    raise ValueError(f"source {source_id!r} introuvable dans {state.source_collection!r}")

                subject_doc = None
                if subject_id:
                    subject_doc = svc.get_document(state.subject_collection, subject_id)
                    if subject_doc is None:
                        raise ValueError(
                            f"subject {subject_id!r} introuvable dans {state.subject_collection!r}"
                        )

                system_prompt = build_tools_system_prompt(
                    source_id=source_id,
                    source_doc=source_doc,
                    subject_id=subject_id,
                    subject_doc=subject_doc,
                    schema=schema,
                )
                messages = [{"role": "user", "content": state.prompt}]

                reply, stats = None, None
                for attempt in range(1, state.max_retries + 1):
                    reply, stats = provider.call(
                        system_prompt=system_prompt,
                        messages=messages,
                        temperature=state.temperature,
                    )
                    if reply:
                        break
                    log.warning(
                        "[tools.run] cellule %s/%s — réponse vide (tentative %d/%d)",
                        source_id, subject_id, attempt, state.max_retries,
                    )
                else:
                    raise ValueError(f"réponse LLM vide après {state.max_retries} tentative(s)")

                fname = f"{source_id}_{subject_id}.txt" if subject_id else f"{source_id}.txt"
                (state.output_dir / fname).write_text(reply, encoding="utf-8")

                cell.update({
                    "status":        "succeeded",
                    "file":          fname,
                    "prompt_tokens": getattr(stats, "prompt_tokens", 0),
                    "output_tokens": getattr(stats, "output_tokens", 0),
                    "duration_ms":   getattr(stats, "duration_ms", 0),
                })
                with _runs_lock:
                    state.succeeded += 1

            except Exception as exc:
                log.warning(
                    "[tools.run] cellule %s/%s a échoué : %s",
                    source_id, subject_id, exc,
                )
                cell.update({"status": "failed", "error": str(exc)})
                with _runs_lock:
                    state.failed += 1

            with _runs_lock:
                state.cells.append(cell)
                state.completed += 1

        with _runs_lock:
            if state.status != "cancelled":
                state.status = "completed"

    except Exception as exc:
        log.exception("[tools.run] exception non gérée run_id=%s : %s", state.run_id, exc)
        with _runs_lock:
            state.status = "failed"
            state.error  = str(exc)

    finally:
        with _runs_lock:
            state.ended_at = datetime.now(timezone.utc).isoformat()
            _write_meta(state)
        log.info(
            "[tools.run] end run_id=%s status=%s succeeded=%d failed=%d",
            state.run_id, state.status, state.succeeded, state.failed,
        )


# ─────────────────────────────────────────────────────────────────────
# Helpers internes
# ─────────────────────────────────────────────────────────────────────

def _resolve_schema(schema_id: str | None) -> dict | None:
    if not schema_id:
        return None
    schema = activity_storage.get().get_schema(schema_id)
    if schema is None:
        log.warning("[tools.run] schéma %r introuvable — ignoré", schema_id)
    return schema


def _state_to_dict(state: RunState) -> dict:
    return {
        "run_id":             state.run_id,
        "task_slug":          state.task_slug,
        "prompt":             state.prompt,
        "temperature":        state.temperature,
        "source_collection":  state.source_collection,
        "source_ids":         state.source_ids,
        "subject_collection": state.subject_collection,
        "subject_ids":        state.subject_ids,
        "schema_id":          state.schema_id,
        "skip_self":          state.skip_self,
        "model_name":         state.model_name,
        "max_retries":        state.max_retries,
        "cancel_requested":   state.cancel_requested,
        "output_dir":         str(state.output_dir),
        "status":             state.status,
        "total":              state.total,
        "completed":          state.completed,
        "succeeded":          state.succeeded,
        "failed":             state.failed,
        "cells":              list(state.cells),
        "started_at":         state.started_at,
        "ended_at":           state.ended_at,
        "error":              state.error,
    }


def _write_meta(state: RunState) -> None:
    meta_path = state.output_dir / "_run.meta.json"
    try:
        meta_path.write_text(
            json.dumps(_state_to_dict(state), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        log.warning("[tools.run] écriture meta échouée : %s", exc)

"""Commandes bus `tools` — atelier utilitaire, pas de MCP, pas de scénario.

Exposition HTTP uniquement. Consulté depuis simweb (section Tools).
"""
from simphonia.core import command
from simphonia.services import configuration_service, tools_service
from simphonia.services.tools_service import runner

TOOLS_BUS = "tools"


# ── registre + documents ─────────────────────────────────────────

@command(
    bus=TOOLS_BUS,
    code="collections.list",
    description="Liste les collections exposables (lecture de `task_collection`)",
)
def collections_list_command() -> list[str]:
    return tools_service.get().list_exposable_collections()


@command(
    bus=TOOLS_BUS,
    code="ids.list",
    description="Liste les `_id` d'une collection autorisée",
)
def ids_list_command(collection_name: str) -> list[str]:
    return tools_service.get().list_ids(collection_name)


@command(
    bus=TOOLS_BUS,
    code="get_document",
    description="Retourne un document complet (schemaless) d'une collection autorisée",
)
def get_document_command(collection_name: str, _id: str) -> dict | None:
    return tools_service.get().get_document(collection_name, _id)


# ── tasks (prompts réutilisables) ────────────────────────────────

@command(
    bus=TOOLS_BUS,
    code="tasks.list",
    description="Liste les tasks stockées",
)
def tasks_list_command() -> list[dict]:
    return tools_service.get().list_tasks()


@command(
    bus=TOOLS_BUS,
    code="tasks.get",
    description="Retourne une task stockée",
)
def tasks_get_command(slug: str) -> dict | None:
    return tools_service.get().get_task(slug)


@command(
    bus=TOOLS_BUS,
    code="tasks.put",
    description="Upsert d'une task (slug + prompt + temperature)",
)
def tasks_put_command(slug: str, prompt: str, temperature: float) -> dict:
    return tools_service.get().put_task(slug, prompt, temperature)


@command(
    bus=TOOLS_BUS,
    code="tasks.delete",
    description="Supprime une task",
)
def tasks_delete_command(slug: str) -> bool:
    return tools_service.get().delete_task(slug)


# ── run + status ──────────────────────────────────────────────────

@command(
    bus=TOOLS_BUS,
    code="run",
    description="Démarre un run tools en thread background. Retourne `{run_id}` immédiatement.",
)
def run_command(
    task_slug: str,
    prompt: str,
    temperature: float,
    source_collection: str,
    source_ids: list[str],
    subject_collection: str | None = None,
    subject_ids: list[str] | None = None,
    schema_id: str | None = None,
    skip_self: bool = True,
) -> dict:
    svc_cfg = configuration_service.section("services.tools_service") or {}
    run_id = runner.start_run(
        task_slug=task_slug,
        prompt=prompt,
        temperature=temperature,
        source_collection=source_collection,
        source_ids=source_ids,
        subject_collection=subject_collection,
        subject_ids=subject_ids,
        schema_id=schema_id,
        skip_self=skip_self,
        model_name=svc_cfg.get("model"),
        output_dir_root=svc_cfg.get("output_dir", "output"),
        max_retries=int(svc_cfg.get("max_retries", 3)),
    )
    return {"run_id": run_id}


@command(
    bus=TOOLS_BUS,
    code="status",
    description="Retourne l'état courant d'un run (pour polling de progress bar)",
)
def status_command(run_id: str) -> dict | None:
    return runner.get_run_status(run_id)


@command(
    bus=TOOLS_BUS,
    code="cancel",
    description="Demande l'interruption d'un run en cours — prise en compte entre deux cellules",
)
def cancel_command(run_id: str) -> bool:
    return runner.cancel_run(run_id)

"""Builder system prompt dédié au tools_service.

Format minimaliste, volontairement déconnecté de `activity_service.context_builder` :
le tools_service ne joue pas à un jeu — il prépare des données. Pas de scène,
pas de règles, pas de knowledge, pas de fiche de personnage au sens scénario.

Structure produite :

    ## SOURCE: <source_id>
    <json.dumps(source_doc, indent=2)>

    ## SUBJECT: <subject_id>             # si subject fourni
    <json.dumps(subject_doc, indent=2)>

    <bloc schéma JSON>                   # si schéma fourni

Le user prompt (la commande saisie) est géré séparément par l'appelant.
"""
import json


def _dump(doc: dict) -> str:
    """Sérialisation uniforme : JSON indenté, pas de stringification ASCII."""
    return json.dumps(doc, ensure_ascii=False, indent=2)


def _format_schema_block(schema: dict) -> str:
    """Formate un schéma `activity_storage.schemas` (`{prompt, payload}`) en bloc.

    Même convention que `activity_service.context_builder._append_schemas` —
    première ligne de consigne, puis prompt du schéma, puis payload.
    """
    lines = [
        "Réponds UNIQUEMENT en JSON valide respectant ce schéma. "
        "Ne l'encadre pas de bloc de code markdown."
    ]
    prompt_text = (schema.get("prompt") or "").strip()
    if prompt_text:
        lines.append(prompt_text)
    payload = schema.get("payload")
    if payload is not None:
        lines.append(payload if isinstance(payload, str) else _dump(payload))
    return "\n".join(lines)


def build_tools_system_prompt(
    source_id: str,
    source_doc: dict,
    subject_id: str | None = None,
    subject_doc: dict | None = None,
    schema: dict | None = None,
) -> str:
    """Compose le system prompt d'une cellule tools_service.

    - `source_id` / `source_doc` : obligatoires
    - `subject_id` / `subject_doc` : cohérents (les deux fournis ou les deux None)
    - `schema` : structure `{prompt, payload}` issue de `activity_storage.schemas`
    """
    parts = [f"## SOURCE: {source_id}\n{_dump(source_doc)}"]

    if subject_id and subject_doc is not None:
        parts.append(f"## SUBJECT: {subject_id}\n{_dump(subject_doc)}")

    if schema:
        parts.append(_format_schema_block(schema))

    return "\n\n".join(parts)

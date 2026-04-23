"""Tests unitaires — `tools_service.builder.build_tools_system_prompt`."""
from simphonia.services.tools_service.builder import build_tools_system_prompt


def test_source_only():
    prompt = build_tools_system_prompt(
        source_id="antoine",
        source_doc={"_id": "antoine", "prénom": "Antoine"},
    )
    assert prompt.startswith("## SOURCE: antoine\n")
    assert '"_id": "antoine"' in prompt
    assert '"prénom": "Antoine"' in prompt  # UTF-8 préservé (ensure_ascii=False)
    assert "SUBJECT" not in prompt


def test_source_plus_subject():
    prompt = build_tools_system_prompt(
        source_id="manon",
        source_doc={"_id": "manon"},
        subject_id="antoine",
        subject_doc={"_id": "antoine", "presentation": "Salut, moi c'est Antoine."},
    )
    assert "## SOURCE: manon" in prompt
    assert "## SUBJECT: antoine" in prompt
    assert prompt.index("SOURCE") < prompt.index("SUBJECT")
    assert "Salut, moi c'est Antoine." in prompt


def test_subject_id_without_doc_is_ignored():
    # Contrat : subject_id et subject_doc sont cohérents (les deux ou aucun).
    # Si subject_doc manque, on n'insère pas la section (sécurité).
    prompt = build_tools_system_prompt(
        source_id="s", source_doc={"_id": "s"},
        subject_id="sub", subject_doc=None,
    )
    assert "SUBJECT" not in prompt


def test_with_schema_payload_dict():
    schema = {
        "prompt": "Retourne un objet JSON avec deux clés.",
        "payload": {"type": "object", "properties": {"x": {"type": "string"}}},
    }
    prompt = build_tools_system_prompt(
        source_id="s", source_doc={"_id": "s"},
        schema=schema,
    )
    assert "Réponds UNIQUEMENT en JSON valide" in prompt
    assert "Retourne un objet JSON avec deux clés." in prompt
    assert '"properties"' in prompt  # payload dict sérialisé


def test_with_schema_payload_str():
    schema = {"prompt": "", "payload": "schéma inline en markdown"}
    prompt = build_tools_system_prompt(
        source_id="s", source_doc={"_id": "s"},
        schema=schema,
    )
    assert "schéma inline en markdown" in prompt


def test_full_combo_order():
    """Ordre strict : SOURCE > SUBJECT > schéma."""
    schema = {"prompt": "S_PROMPT", "payload": "S_PAYLOAD"}
    prompt = build_tools_system_prompt(
        source_id="src",
        source_doc={"_id": "src"},
        subject_id="sub",
        subject_doc={"_id": "sub"},
        schema=schema,
    )
    i_source = prompt.index("## SOURCE:")
    i_subject = prompt.index("## SUBJECT:")
    i_schema  = prompt.index("S_PROMPT")
    assert i_source < i_subject < i_schema


def test_no_schema_no_block():
    prompt = build_tools_system_prompt(
        source_id="s", source_doc={"_id": "s"},
    )
    assert "Réponds UNIQUEMENT en JSON" not in prompt

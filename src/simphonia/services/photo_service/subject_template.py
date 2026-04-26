"""Résolution du `subject_template` configuré dans `services.photo`.

Le template est une string contenant des placeholders `{path.dotted}` qui
référencent des clés du JSON d'une fiche personnage (schemaless). La résolution
walk dotted ; les placeholders non résolvables provoquent la suppression du
**segment** qui les contient (séparation par virgule).

Voir `documents/photo_service.md` § 4 pour le cahier des charges complet.
"""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER_RE = re.compile(r"\{([\w.]+)\}")


def _walk_dotted(node: Any, path: str) -> Any:
    """Walk un chemin pointé sur un dict imbriqué. Retourne `None` si un maillon
    intermédiaire n'est pas un dict ou si une clé est absente.
    """
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _is_resolved(value: Any) -> bool:
    """Une valeur est considérée résolue si elle est non-`None`, non-vide
    (string), et de type scalaire (str/int/float/bool — pas dict/list).
    """
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    if isinstance(value, (dict, list)):
        return False
    return True


def resolve_subject_template(template: str, character: dict) -> str:
    """Résout un `subject_template` sur une fiche personnage schemaless.

    Mécanique :
      1. Le template est découpé en **segments** sur la virgule.
      2. Pour chaque segment, les placeholders `{path.dotted}` sont collectés.
      3. Si tous les placeholders du segment se résolvent, le segment est
         conservé avec les substitutions appliquées.
      4. Si au moins un placeholder est non résolu (clé absente / `None` /
         string vide / valeur structurée), le segment **entier** est dropped.
      5. Les segments retenus sont joints par `", "` après strip des espaces.

    Cette stratégie permet à Valère d'étoffer le template au fil de l'eau sans
    risquer de produire des fragments comme `"yeux , cheveux ..."` quand un
    champ manque dans la fiche.

    Args:
        template: chaîne contenant des placeholders `{path.dotted}`.
        character: dict de fiche personnage (schemaless).

    Returns:
        Chaîne résolue avec uniquement les segments dont tous les placeholders
        se résolvent. Retourne une chaîne vide si aucun segment ne tient.
    """
    kept: list[str] = []
    for segment in template.split(","):
        placeholders = _PLACEHOLDER_RE.findall(segment)
        resolved_segment = segment
        skip = False
        for ph in placeholders:
            value = _walk_dotted(character, ph)
            if not _is_resolved(value):
                skip = True
                break
            resolved_segment = resolved_segment.replace("{" + ph + "}", str(value))
        if not skip:
            kept.append(resolved_segment.strip())
    return ", ".join(kept)

"""Parsing / rendering du markdown sectionné échangé entre le LLM-joueur et
`photo_service`.

Format : sections introduites par `# nom_section` au début de ligne, contenu
multilignes jusqu'à la prochaine section ou la fin du document. La liste des
sections est **ouverte** — le service ne valide pas un set fermé, il concatène
ce qu'il reçoit (modulo overrides pour `take_selfy` sur `style` et `sujet`).

Voir `documents/photo_service.md` § 1.3 pour le cahier des charges.
"""

from __future__ import annotations


def parse_sections(markdown: str) -> dict[str, str]:
    """Parse un markdown sectionné en dict ordonné `nom → contenu`.

    Une section est introduite par une ligne commençant par `# ` (dièse +
    espace). Le contenu multilignes qui suit est associé à cette section
    jusqu'à la prochaine section ou la fin du document. Le contenu est
    `strip()` (espaces et lignes vides en début/fin retirés).

    Tout ce qui précède la première section est ignoré (préambule éventuel).

    Args:
        markdown: chaîne markdown.

    Returns:
        Dict `nom_section → contenu` dans l'ordre d'apparition.
    """
    sections: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []

    for line in markdown.splitlines():
        if line.startswith("# "):
            if current_name is not None:
                sections[current_name] = "\n".join(current_lines).strip()
            current_name = line[2:].strip()
            current_lines = []
        else:
            if current_name is not None:
                current_lines.append(line)

    if current_name is not None:
        sections[current_name] = "\n".join(current_lines).strip()

    return sections


def render_sections(sections: dict[str, str]) -> str:
    """Sérialise un dict de sections en markdown.

    Format : `# nom\\ncontenu` pour chaque section, séparées par une ligne
    vide. L'ordre des clés du dict est préservé (garanti par Python 3.7+).
    """
    parts = [f"# {name}\n{content}" for name, content in sections.items()]
    return "\n\n".join(parts)


def merge_with_overrides(
    sections: dict[str, str],
    overrides: dict[str, str],
) -> dict[str, str]:
    """Fusionne un dict de sections avec un dict d'overrides.

    Les overrides **écrasent** les sections de même nom et apparaissent **en
    tête** du dict résultant. Les sections originales non concernées par un
    override sont préservées dans leur ordre d'apparition.

    Use case `take_selfy` : `overrides = {"style": ..., "sujet": ...}` fournis
    par le service ; `sections` = parsing du markdown LLM. Résultat : style +
    sujet figés au début, suivis de tenue/attitude/pose/... du LLM.
    """
    result: dict[str, str] = {}
    for key, value in overrides.items():
        result[key] = value
    for key, value in sections.items():
        if key not in result:
            result[key] = value
    return result

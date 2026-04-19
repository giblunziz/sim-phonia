"""Utilitaires de parsing pour réponses LLM — JSON et Markdown.

Port de symphonie.utils.parser.
"""
import json
import re


def strip_markdown_fences(text: str) -> str:
    """Retire les blocs ```json ... ``` ou ``` ... ``` d'une réponse LLM."""
    cleaned = re.sub(r"```(?:json|JSON)?\s*\n?", "", text)
    return cleaned.strip()


def parse_llm_json(reply: str) -> dict | None:
    """Parse un JSON depuis une réponse LLM.

    Gère les blocs markdown (```json ... ```), les JSON bruts, et les blocs multiples
    (ne garde que le premier JSON équilibré trouvé).
    """
    reply = strip_markdown_fences(reply)

    try:
        return json.loads(reply)
    except json.JSONDecodeError:
        pass

    start = reply.find('{')
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(reply)):
        c = reply[i]
        if escape:
            escape = False
            continue
        if c == '\\' and in_string:
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                candidate = reply[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None

    return None

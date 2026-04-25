"""Commandes bus `activity` — orchestrateur de session MJ-driven.

Les commandes `give_turn`, `next_round`, `end` sont également exposées en MCP
avec `mcp_role="mj"` — elles sont accessibles à un LLM MJ autonome via
`/sse/mj`, invisibles des joueurs sur `/sse`.
"""

from simphonia.core import command
from simphonia.services.activity_service import engine

ACTIVITY_BUS = "activity"


@command(bus=ACTIVITY_BUS, code="run",
         description="Initialise une session d'activité depuis une instance et retourne le dashboard MJ")
def run(instance_id: str, human_player: str | None = None) -> dict:
    return engine.run(instance_id, human_player=human_player)


@command(bus=ACTIVITY_BUS, code="resume",
         description="Reprend un run existant (reconstruit le SessionState depuis activity_runs)")
def resume(run_id: str) -> dict:
    return engine.resume(run_id)


@command(
    bus=ACTIVITY_BUS,
    code="give_turn",
    description="Donne la parole à un joueur (LLM) — non bloquant, résultat via SSE",
    mcp=True,
    mcp_role="mj",
    mcp_description=(
        "Donne la parole à un participant de l'activité. Compose son instruction : décris-lui "
        "la situation, ce qu'on attend de lui, sans jamais lui donner de consigne mécanique. "
        "Non bloquant : le joueur répondra via un exchange séparé."
    ),
    mcp_params={
        "type": "object",
        "properties": {
            "session_id":  {"type": "string", "description": "Identifiant de la session d'activité en cours"},
            "target":      {"type": "string", "description": "Slug du joueur à qui donner la parole"},
            "instruction": {"type": "string", "description": "Instruction narrative (whisper optionnel)"},
        },
        "required": ["session_id", "target"],
    },
)
def give_turn(session_id: str, target: str, instruction: str | None = None) -> dict:
    return engine.give_turn(session_id, target, instruction)


@command(
    bus=ACTIVITY_BUS,
    code="next_round",
    description="Passe au round suivant (incrémente le compteur, charge l'event)",
    mcp=True,
    mcp_role="mj",
    mcp_description=(
        "Passe au round suivant quand le round courant est résolu. Incrémente le compteur de tour. "
        "Si `max_rounds` est atteint, l'activité se termine automatiquement."
    ),
    mcp_params={
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Identifiant de la session d'activité en cours"},
        },
        "required": ["session_id"],
    },
)
def next_round(session_id: str) -> dict:
    return engine.next_round(session_id)


@command(
    bus=ACTIVITY_BUS,
    code="submit_human_turn",
    description="Intègre la saisie d'un joueur humain dans l'activité (HITL — non exposée en MCP)",
)
def submit_human_turn(
    session_id: str,
    target:     str,
    to:         str,
    talk:       str,
    actions:    str,
) -> dict:
    return engine.submit_human_turn(session_id, target, to, talk, actions)


@command(
    bus=ACTIVITY_BUS,
    code="end",
    description="Termine l'activité, persiste l'état final, ferme la session",
    mcp=True,
    mcp_role="mj",
    mcp_description=(
        "Termine l'activité immédiatement. Persiste l'état final. Utilise cette commande "
        "quand tu juges que l'activité est arrivée à sa conclusion narrative, ou que "
        "tout ce qui devait être joué l'a été."
    ),
    mcp_params={
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Identifiant de la session d'activité à clore"},
        },
        "required": ["session_id"],
    },
)
def end(session_id: str) -> dict:
    return engine.end(session_id)

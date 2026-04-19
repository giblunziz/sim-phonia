"""Commandes bus `activity` — orchestrateur de session MJ-driven."""

from simphonia.core import command
from simphonia.services.activity_service import engine

ACTIVITY_BUS = "activity"


@command(bus=ACTIVITY_BUS, code="run",
         description="Initialise une session d'activité depuis une instance et retourne le dashboard MJ")
def run(instance_id: str) -> dict:
    return engine.run(instance_id)


@command(bus=ACTIVITY_BUS, code="resume",
         description="Reprend un run existant (reconstruit le SessionState depuis activity_runs)")
def resume(run_id: str) -> dict:
    return engine.resume(run_id)


@command(bus=ACTIVITY_BUS, code="give_turn",
         description="Donne la parole à un joueur (LLM) — non bloquant, résultat via SSE")
def give_turn(session_id: str, target: str, instruction: str | None = None) -> dict:
    return engine.give_turn(session_id, target, instruction)


@command(bus=ACTIVITY_BUS, code="next_round",
         description="Passe au round suivant (incrémente le compteur, charge l'event)")
def next_round(session_id: str) -> dict:
    return engine.next_round(session_id)


@command(bus=ACTIVITY_BUS, code="end",
         description="Termine l'activité, persiste l'état final, ferme la session")
def end(session_id: str) -> dict:
    return engine.end(session_id)

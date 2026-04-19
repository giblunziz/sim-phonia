"""mj_service — orchestration du game-flow d'une activité.

Contrairement aux autres services sim-phonia (multi-stratégies sélectionnées au
bootstrap via YAML), le `mj_service` n'est **pas un singleton**. La stratégie
(`human` / `human_in_loop` / `autonomous`) dépend du `mj_mode` de chaque
`activity_run`, pas d'un choix d'infrastructure global.

Pattern : factory runtime. L'engine appelle `build_mj_service(mode)` à
`activity/run` et stocke l'instance dans `SessionState.mj_service`. La vie du
service = la vie de la session.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simphonia.services.activity_service.engine import SessionState


class MJService(ABC):
    """Contrat commun aux stratégies MJ.

    Les trois méthodes couvrent le cycle de vie d'un run. L'engine les appelle
    aux moments clés ; la stratégie décide quoi faire (rien, résoudre un
    prochain speaker, déclencher une boucle LLM, etc.).
    """

    @abstractmethod
    def on_turn_complete(self, session: "SessionState", exchange: dict) -> None:
        """Appelé par l'engine après chaque tour résolu (exchange ajouté à l'history).

        - `human`         : no-op
        - `human_in_loop` : pré-résout le prochain speaker, publie SSE `mj.next_ready`
        - `autonomous`    : déclenche immédiatement le prochain tour LLM
        """

    @abstractmethod
    def on_next_turn(self, session: "SessionState") -> str | None:
        """Appelé par `mj/next_turn` (humain) ou par la boucle `autonomous`.

        Retourne le slug du prochain speaker à passer à `activity/give_turn`,
        ou `None` si le round est terminé (l'engine enchaîne `next_round` ou
        `end` selon les règles).
        """

    @abstractmethod
    def on_session_end(self, session: "SessionState") -> None:
        """Nettoyage — kill thread (autonomous), log stats, etc."""


def build_mj_service(mode: str) -> MJService:
    """Instancie la stratégie MJ correspondant au `mj_mode`.

    Import des stratégies en lazy (comme dans les autres services du projet) —
    évite de charger les dépendances LLM tant que personne ne démarre un run
    en mode `autonomous`.

    Lève `ValueError` si le mode est inconnu.
    """
    if mode == "human":
        from simphonia.services.mj_service.strategies.human_strategy import HumanMJ
        return HumanMJ()

    # Stratégies à venir — référencées ici pour que l'erreur soit explicite :
    # if mode == "human_in_loop":  # étape #5
    #     ...
    # if mode == "autonomous":     # étape #8
    #     ...

    raise ValueError(
        f"Unknown mj_mode: {mode!r}. Valid (V1): ['human']. "
        f"Planned: ['human_in_loop', 'autonomous']."
    )

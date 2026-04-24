from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from simphonia.core.cascade import Cascade, CascadePosition
from simphonia.core.command import Command
from simphonia.core.errors import CommandNotFound, DispatchError, DuplicateCascade, DuplicateCommand

log = logging.getLogger(__name__)

BusListener = Callable[[dict[str, Any]], None]


class Bus:
    def __init__(self, name: str) -> None:
        self.name = name
        self._commands: dict[str, Command] = {}
        # Cascades stockées par (bus, code, position) → liste triée (priority, discovery_order).
        # Clé : (code, position) → list[Cascade] triée par (priority, discovery_order).
        self._cascades: dict[tuple[str, CascadePosition], list[Cascade]] = {}
        self._cascade_counter: int = 0
        # Listeners observer-pattern : notifiés après chaque dispatch (best-effort, isolés).
        self._listeners: list[BusListener] = []

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def register(self, cmd: Command) -> None:
        if cmd.code in self._commands:
            raise DuplicateCommand(self.name, cmd.code)
        self._commands[cmd.code] = cmd

    def get(self, code: str) -> Command:
        try:
            return self._commands[code]
        except KeyError:
            raise CommandNotFound(self.name, code) from None

    def list(self) -> list[Command]:
        return list(self._commands.values())

    def dispatch(self, code: str, payload: dict[str, Any] | None = None) -> Any:
        cmd = self.get(code)
        try:
            result = cmd.callback(**(payload or {}))
        except (CommandNotFound, DispatchError):
            raise
        except Exception as exc:
            raise DispatchError(self.name, code, exc) from exc

        self._notify_listeners(payload or {})
        return result

    # ------------------------------------------------------------------
    # Listeners (observer pattern)
    # ------------------------------------------------------------------

    def subscribe(self, listener: BusListener) -> None:
        """Enregistre un listener notifié après chaque dispatch sur ce bus.

        Le listener reçoit uniquement le payload du dispatch (pas de code, pas
        de result). Best-effort : exceptions logguées, n'impactent ni le retour
        du dispatch ni les autres listeners. Synchrone : un listener lent
        ralentit l'appelant — à ne jamais oublier.
        """
        self._listeners.append(listener)

    def listeners(self) -> list[BusListener]:
        """Retourne un snapshot de la liste des listeners (pour tests/debug)."""
        return list(self._listeners)

    def _notify_listeners(self, payload: dict[str, Any]) -> None:
        for listener in self._listeners:
            try:
                listener(payload)
            except Exception as exc:
                fn_name = getattr(listener, "__qualname__", repr(listener))
                log.warning(
                    "[bus.%s] listener %s a échoué : %s",
                    self.name, fn_name, exc, exc_info=True,
                )

    # ------------------------------------------------------------------
    # Cascades
    # ------------------------------------------------------------------

    def register_cascade(self, cascade: Cascade) -> None:
        """Enregistre une cascade en maintenant le tri (priority, discovery_order).

        Lève `DuplicateCascade` si le même callback est déjà enregistré pour
        cette (code, position).
        """
        key: tuple[str, CascadePosition] = (cascade.code, cascade.position)
        bucket = self._cascades.setdefault(key, [])

        # Vérifie les doublons par identité du callback.
        fn_name = getattr(cascade.callback, "__qualname__", repr(cascade.callback))
        for existing in bucket:
            if existing.callback is cascade.callback:
                raise DuplicateCascade(
                    self.name, cascade.code, cascade.position, fn_name
                )

        # Injection du discovery_order et reconstruction d'un Cascade immutable.
        order = self._cascade_counter
        self._cascade_counter += 1
        # Dataclass frozen → on crée une nouvelle instance avec discovery_order fixé.
        ordered = Cascade(
            bus_name=cascade.bus_name,
            code=cascade.code,
            position=cascade.position,
            callback=cascade.callback,
            priority=cascade.priority,
            discovery_order=order,
        )

        # Insertion triée par (priority, discovery_order).
        bucket.append(ordered)
        bucket.sort(key=lambda c: (c.priority, c.discovery_order))

    def list_cascades(
        self,
        code: str,
        position: CascadePosition,
    ) -> list[Cascade]:
        """Retourne les cascades enregistrées pour (code, position), triées."""
        key: tuple[str, CascadePosition] = (code, position)
        return list(self._cascades.get(key, []))

    def all_cascades(self) -> dict[tuple[str, CascadePosition], list[Cascade]]:
        """Retourne toutes les cascades (snapshot)."""
        return {k: list(v) for k, v in self._cascades.items()}

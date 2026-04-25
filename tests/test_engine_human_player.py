"""Tests unitaires — résolution du joueur humain (HITL).

Vérifie le helper `_resolve_human_player` :
  - Override session prime sur le scan des fiches
  - Override invalide (slug non listé) → fallback scan + warning
  - Sans override : scan retourne le premier `type=="human"`, warning si plusieurs
  - Aucun humain trouvé → `None`

Cf. documents/human_in_the_loop.md (Q3, Q12).
"""
from __future__ import annotations

from simphonia.services.activity_service.engine import _resolve_human_player


class FakeCharacterService:
    """Stub minimal — types et identifier précâblés.

    `types` : mapping slug → type retourné par `get_type`.
    `identifier_map` : mapping nom (libre) → slug canonique pour `get_identifier`.
    """

    def __init__(self, types: dict[str, str] | None = None,
                 identifier_map: dict[str, str] | None = None) -> None:
        self.types          = types or {}
        self.identifier_map = identifier_map or {}

    def get_type(self, slug: str) -> str:
        return self.types.get(slug, "player")

    def get_identifier(self, name: str) -> str | None:
        return self.identifier_map.get(name)


# ---------------------------------------------------------------------------
#  Override session
# ---------------------------------------------------------------------------

class TestOverrideSession:

    def test_override_valide_listed_in_players(self):
        """Override = slug exact présent dans players → retenu."""
        char_svc = FakeCharacterService(types={"valere": "human"})
        result   = _resolve_human_player(char_svc, ["valere", "antoine"], "valere")
        assert result == "valere"

    def test_override_resolu_via_get_identifier(self):
        """Override = nom libre → résolu via get_identifier."""
        char_svc = FakeCharacterService(
            types={"valere": "human"},
            identifier_map={"Valère": "valere"},
        )
        result = _resolve_human_player(char_svc, ["valere", "antoine"], "Valère")
        assert result == "valere"

    def test_override_prime_sur_scan_fiche(self):
        """Override prime même si une autre fiche a type=human."""
        char_svc = FakeCharacterService(types={
            "antoine": "human",   # serait pris par le scan
            "valere":  "player",  # pas human dans la fiche
        })
        # Mais override force valere
        result = _resolve_human_player(char_svc, ["antoine", "valere"], "valere")
        assert result == "valere"

    def test_override_non_liste_dans_players_warning_fallback(self, caplog):
        """Override pointe vers un slug absent de players → warning + fallback scan."""
        char_svc = FakeCharacterService(types={"antoine": "human"})
        with caplog.at_level("WARNING"):
            result = _resolve_human_player(char_svc, ["antoine", "elise"], "valere")
        # Fallback : scan trouve antoine human
        assert result == "antoine"
        assert any("non listé dans les participants" in r.message for r in caplog.records)

    def test_override_non_liste_pas_de_human_dans_scan(self, caplog):
        """Override invalide + aucun human dans le scan → None."""
        char_svc = FakeCharacterService(types={"antoine": "player", "elise": "player"})
        with caplog.at_level("WARNING"):
            result = _resolve_human_player(char_svc, ["antoine", "elise"], "valere")
        assert result is None
        assert any("non listé dans les participants" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
#  Scan de fiches (fallback)
# ---------------------------------------------------------------------------

class TestScanFallback:

    def test_aucun_override_un_seul_human(self):
        """Pas d'override, un seul participant human → retourné."""
        char_svc = FakeCharacterService(types={"valere": "human", "antoine": "player"})
        result   = _resolve_human_player(char_svc, ["valere", "antoine"], None)
        assert result == "valere"

    def test_aucun_override_plusieurs_humans_warning(self, caplog):
        """Plusieurs humans détectés → premier match + warning."""
        char_svc = FakeCharacterService(types={
            "valere":  "human",
            "antoine": "human",
            "elise":   "player",
        })
        with caplog.at_level("WARNING"):
            result = _resolve_human_player(char_svc, ["valere", "antoine", "elise"], None)
        assert result == "valere"
        assert any("type='human'" in r.message for r in caplog.records)

    def test_aucun_override_aucun_human(self):
        """Aucun humain → None."""
        char_svc = FakeCharacterService(types={"antoine": "player", "elise": "player"})
        result   = _resolve_human_player(char_svc, ["antoine", "elise"], None)
        assert result is None

    def test_aucun_override_players_vide(self):
        """Liste de joueurs vide → None."""
        char_svc = FakeCharacterService()
        result   = _resolve_human_player(char_svc, [], None)
        assert result is None


# ---------------------------------------------------------------------------
#  Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_override_string_vide_traite_comme_absent(self):
        """`human_player=""` équivaut à pas d'override → scan."""
        char_svc = FakeCharacterService(types={"valere": "human"})
        result   = _resolve_human_player(char_svc, ["valere"], "")
        # String vide est falsy en Python → scan, qui trouve valere
        assert result == "valere"

    def test_override_pointe_sur_player_listed(self):
        """Override pointe sur un player non-human listé : retenu (l'override prime sur le type fiche)."""
        char_svc = FakeCharacterService(types={"antoine": "player"})
        result   = _resolve_human_player(char_svc, ["antoine"], "antoine")
        assert result == "antoine"

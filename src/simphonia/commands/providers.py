"""Commandes bus `providers` — introspection du registre de providers LLM."""

from simphonia.core import command
from simphonia.services import provider_registry

PROVIDERS_BUS = "providers"


@command(bus=PROVIDERS_BUS, code="list",
         description="Retourne la liste des slugs de providers enregistrés")
def providers_list() -> list[str]:
    return provider_registry.list_names()

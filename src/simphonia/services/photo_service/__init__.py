"""PhotoService — génération et diffusion de photos par les personnages.

Interface + factory qui instancie la stratégie (`z_image_turbo`, futur `comfyui`, …)
sélectionnée via la configuration YAML (`services.photo`).

Voir `documents/photo_service.md` pour le cahier des charges complet (commandes
MCP `take_shoot` / `take_selfy`, format markdown sectionné, `subject_template`
schemaless, persistance, mode async hybride).
"""

import logging
from abc import ABC, abstractmethod

log = logging.getLogger("simphonia.photo")


class PhotoService(ABC):
    """Contrat schemaless : les commandes acceptent et renvoient des `dict` bruts.

    Les deux entrées principales (`take_shoot`, `take_selfy`) acceptent un
    `markdown` produit par le LLM-joueur (sections nommées `# style`, `# sujet`,
    `# tenue`, `# attitude`, …). Voir `documents/photo_service.md` § 1.3.

    La génération est asynchrone : ces méthodes retournent immédiatement un ack
    `{"status": "queued", "photo_id": "..."}`. L'image est produite en
    arrière-plan ; quand elle est prête, le service publie un événement
    `photo.published` sur le bus `photo`.
    """

    @abstractmethod
    def take_shoot(
        self,
        markdown: str,
        from_char: str,
        session_id: str,
        activity_id: str | None = None,
    ) -> dict:
        """Génère une photo de scène libre à partir d'un prompt markdown.

        Le LLM est libre sur toutes les sections — aucune n'est imposée ni
        écrasée par le service.

        Retourne `{"status": "queued", "photo_id": "..."}` immédiatement.
        """

    @abstractmethod
    def take_selfy(
        self,
        markdown: str,
        from_char: str,
        session_id: str,
        activity_id: str | None = None,
    ) -> dict:
        """Génère un autoportrait à partir d'un prompt markdown.

        Les sections `# style` et `# sujet` sont écrasées par le service pour
        garantir la cohérence visuelle inter-selfies :

        - `# style` ← config YAML `services.photo.style_prefix.take_selfy`
        - `# sujet` ← `subject_template` résolu sur la fiche de `from_char`

        Le LLM garde la main sur les sections variables (`# tenue`,
        `# attitude`, `# pose`, `# arriere_plan`, `# ambiance`, …).

        Retourne `{"status": "queued", "photo_id": "..."}` immédiatement.
        """

    @abstractmethod
    def get_photo(self, photo_id: str) -> dict | None:
        """Retourne les métadonnées + le `file_path` d'une photo.

        Renvoie `None` si l'identifiant est inconnu. Le format du dict suit le
        schéma `photos` documenté dans `documents/photo_service.md` § 5.
        """


def build_photo_service(service_config: dict) -> PhotoService:
    """Instancie la stratégie configurée (`services.photo` section).

    Import dynamique pour éviter de charger les dépendances lourdes (torch,
    diffusers, …) tant que la stratégie correspondante n'est pas sélectionnée.
    """
    strategy = service_config.get("strategy", "z_image_turbo")

    if strategy == "z_image_turbo":
        from simphonia.services.photo_service.strategies.z_image_turbo_strategy import (
            ZImageTurboPhotoService,
        )
        return ZImageTurboPhotoService(service_config)

    raise ValueError(f"Unknown photo_service strategy: {strategy!r}")


_instance: PhotoService | None = None


def init(service_config: dict) -> None:
    """Construit l'instance du service selon la config donnée. Idempotent."""
    global _instance
    if _instance is None:
        _instance = build_photo_service(service_config)


def get() -> PhotoService:
    """Retourne l'instance du service. `init()` doit avoir été appelé auparavant."""
    if _instance is None:
        raise RuntimeError("photo_service not initialized — call init() first")
    return _instance

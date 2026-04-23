"""DefaultChatService — stratégie de dialogue avec appel LLM et schéma JSON.

Gère le cycle de vie des sessions (start / reply / stop) et valide les
participants via `character_service`. Le provider LLM est appelé à chaque
tour pour générer la réponse du personnage cible.
"""

import json
import logging
import uuid
from datetime import datetime

from simphonia.core import default_registry
from simphonia.core.errors import CharacterNotFound, InvalidParticipant, LLMError, SessionNotFound
from simphonia.core.mcp import mcp_tool_definitions, mcp_tool_hints
from simphonia.providers.base import LLMProvider, ToolExecutor
from simphonia.services.activity_service.context_builder import build_system_prompt
from simphonia.services.chat_service import ChatService
from simphonia.services.chat_service.types import DialogueMessage, DialogueState
from simphonia.services import memory_service


_TALK_SCHEMA = (
    'Ta réponse finale doit être UNIQUEMENT un objet JSON valide, sans texte avant ni après.\n'
    'Format obligatoire :\n'
    '{"talk": "Ta réponse complète en un seul bloc de texte."}\n\n'
    'IMPORTANT :\n'
    '- "talk" est une SEULE chaîne de caractères, PAS un tableau.\n'
    '- Produis UNE SEULE réponse cohérente. PAS de variantes, PAS d\'alternatives.\n'
    '- Reste en personnage. Réponds naturellement, comme dans une vraie conversation.\n\n'
    'Champs futurs (non requis maintenant) : from, to, actions, mood, inner, '
    'expected, noticed, body, memory'
)


class DefaultChatService(ChatService):
    def __init__(
        self,
        provider: LLMProvider,
        provider_name: str,
        logger: logging.Logger,
    ) -> None:
        self._provider = provider
        self._provider_name = provider_name
        self._log = logger
        self._sessions: dict[str, DialogueState] = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validate_character(self, name: str) -> None:
        """Lève CharacterNotFound si le personnage n'existe pas."""
        from simphonia.services import character_service

        if name not in character_service.get().get_character_list():
            raise CharacterNotFound(name)

    def _build_system_prompt(
        self,
        to_card: dict,
        to: str,
        from_char: str,
        human: bool,
        role: str,
        scene: dict,
    ) -> str:
        """Compose le system prompt via `activity_service.context_builder` pour
        partager la même logique que l'`activity_engine` (scène + knowledge +
        fiche perso). L'interlocuteur et le schéma JSON `{talk}` restent
        propres au chat simple — ajoutés en suffixe.
        """
        from simphonia.services import character_storage

        knowledge_entries = character_storage.get().list_knowledge(filter={"from": to})

        body = build_system_prompt(
            player=to,
            instance=None,
            activity=None,
            scene=scene,
            character=to_card,
            knowledge_entries=knowledge_entries,
            system_schemas=None,
        )

        memory_hint = mcp_tool_hints(role=role)
        interlocutor = (
            f"Tu parles avec un humain nommé {from_char}."
            if human
            else f"Tu parles avec le personnage {from_char}."
        )

        parts = []
        if memory_hint:
            parts.append(memory_hint)
        parts.append(body)
        parts.append(interlocutor)
        parts.append(_TALK_SCHEMA)
        return "\n\n".join(parts)

    def _get_mcp_tools(self, role: str) -> list[dict]:
        """Tool definitions (format provider-agnostic) pour les commandes d'un rôle donné.

        Le `role` est dérivé depuis `character.type` via `character_service.get_type()`
        par les callers (start / reply / auto_reply).
        """
        return mcp_tool_definitions(role=role)

    def _make_tool_executor(self, from_char: str, state: "DialogueState | None" = None) -> ToolExecutor:
        """Retourne un exécuteur de tools avec from_char injecté.

        Si `state` est fourni, les confirmations `memorize` sont ajoutées dans
        `state.memorize_log[from_char]` pour ré-injection dans le prompt à
        chaque tour (cohérence narrative).
        """
        def execute(name: str, args: dict) -> str:
            if name == "recall":
                from simphonia.services import character_service
                about_raw  = args.get("about", "").strip()
                about_slug = character_service.get().get_identifier(about_raw) or about_raw.lower()
                context    = args.get("context", "").strip()
                memories = memory_service.get().recall(
                    from_char=from_char,
                    context=context,
                    about=about_slug or None,
                )
                if not memories:
                    return f"Je n'ai aucun souvenir de {about_raw or 'cette personne'}."
                lines = [f"# Vos souvenirs à propos de {about_raw}"]
                for m in memories:
                    lines.append(f"- {m['value']}")
                return "\n".join(lines)

            if name == "memorize":
                from simphonia.commands.memory import format_memorize_markdown
                notes  = args.get("notes") or []
                result = memory_service.get().memorize(
                    from_char=from_char, notes=notes,
                    activity="chat", scene="chat",
                )
                markdown = format_memorize_markdown(result)
                if state is not None:
                    state.memorize_log.setdefault(from_char, []).append(markdown)
                return markdown

            return f"Outil inconnu : {name}"
        return execute

    def _build_messages(
        self,
        history: list[DialogueMessage],
        to_speaker: str,
        memorize_log: list[str] | None = None,
    ) -> list[dict]:
        messages = []
        # Ré-injection des mémorisations récentes du speaker (cohérence narrative).
        if memorize_log:
            content = "## Tes mémorisations récentes\n\n" + "\n\n---\n\n".join(memorize_log)
            messages.append({"role": "user", "content": content})
        for msg in history:
            if msg.speaker == to_speaker:
                messages.append({"role": "assistant", "content": msg.content})
            else:
                messages.append({"role": "user", "content": f"[{msg.speaker}] {msg.content}"})
        return messages

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Retire les balises ```json ... ``` ou ``` ... ``` si présentes."""
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            inner = lines[1:] if lines[-1].strip() == "```" else lines[1:]
            if inner and inner[-1].strip() == "```":
                inner = inner[:-1]
            stripped = "\n".join(inner)
        return stripped

    def _dispatch_said(self, session_id: str, from_char: str, to: str, content: str) -> None:
        """Publie chat.said sur le bus — fire-and-forget, erreur ignorée."""
        try:
            default_registry().get("chat").dispatch("said", {
                "session_id": session_id,
                "from_char": from_char,
                "to": to,
                "content": content,
            })
        except Exception as exc:
            self._log.warning("[said] dispatch échoué : %s", exc)

    def _publish_sse(self, session_id: str, from_char: str, to: str, content: str) -> None:
        """Publie directement sur SSE sans passer par le bus (pas de re-dispatch)."""
        try:
            from simphonia.http import sse
            sse.publish(session_id, {
                "type": "said",
                "session_id": session_id,
                "from_char": from_char,
                "to": to,
                "content": content,
            })
        except Exception as exc:
            self._log.warning("[sse] publish échoué : %s", exc)

    def _call_llm(
        self,
        system_prompt: str,
        messages: list[dict],
        from_char: str | None = None,
        state: "DialogueState | None" = None,
    ) -> str:
        if from_char:
            from simphonia.services import character_service
            role     = character_service.get().get_type(from_char)
            tools    = self._get_mcp_tools(role)
            executor = self._make_tool_executor(from_char, state)
        else:
            tools    = None
            executor = None
        reply_text, stats = self._provider.call(system_prompt, messages, tools=tools, tool_executor=executor)
        if reply_text is None:
            raise LLMError("Le provider LLM n'a retourné aucune réponse")
        try:
            data = json.loads(self._strip_markdown_fences(reply_text))
            talk = data.get("talk")
            if talk is None:
                self._log.warning("Champ 'talk' absent dans la réponse JSON — fallback texte brut")
                return reply_text.strip()
            # talk peut être str ou list — normaliser en str
            if isinstance(talk, str):
                return talk
            if isinstance(talk, list) and talk:
                # Sécurité : si le LLM a quand même produit un tableau,
                # prendre uniquement le premier élément (pas de concaténation d'alternatives)
                self._log.warning("'talk' est un tableau (%d éléments) — prise du premier uniquement", len(talk))
                return str(talk[0])
            self._log.warning("'talk' vide — fallback texte brut")
            return reply_text.strip()
        except (json.JSONDecodeError, ValueError):
            self._log.warning("Réponse LLM non-JSON — fallback texte brut")
            return reply_text.strip()

    # ------------------------------------------------------------------
    # Interface publique
    # ------------------------------------------------------------------

    def start(
        self,
        from_char: str,
        to: str,
        say: str,
        human: bool = False,
        scene_id: str | None = None,
    ) -> dict:
        """Démarre une nouvelle session de dialogue après validation des participants."""
        from simphonia.services import activity_storage, character_service

        self._validate_character(from_char)
        self._validate_character(to)

        scene: dict = {}
        if scene_id:
            resolved = activity_storage.get().get_scene(scene_id)
            if resolved:
                scene = resolved
            else:
                self._log.warning("[start] scène %r introuvable — ignorée", scene_id)

        session_id = str(uuid.uuid4())
        state = DialogueState(
            session_id=session_id,
            participants=(from_char, to),
            history=[],
            provider_ref=self._provider_name,
            scene=scene,
        )
        state.history.append(
            DialogueMessage(
                speaker=from_char,
                content=say,
                timestamp=datetime.utcnow(),
            )
        )
        self._sessions[session_id] = state

        self._log.info(
            "[start] session=%s from=%r to=%r human=%s — %r",
            session_id,
            from_char,
            to,
            human,
            say,
        )

        # Générer la réponse de `to` via LLM (sauf si to est un humain — non géré MVP)
        to_card = character_service.get().get_character(to)
        to_role = character_service.get().get_type(to)
        system_prompt = self._build_system_prompt(to_card, to, from_char, human, to_role, state.scene)
        messages = self._build_messages(state.history, to, memorize_log=state.memorize_log.get(to))
        try:
            reply_text = self._call_llm(system_prompt, messages, from_char=to, state=state)
            state.history.append(DialogueMessage(
                speaker=to,
                content=reply_text,
                timestamp=datetime.utcnow(),
            ))
            self._log.info("[start] reply from=%r — %r", to, reply_text)
            if not human:
                self._dispatch_said(session_id, from_char=to, to=from_char, content=reply_text)
        except LLMError as e:
            self._log.error("[start] LLM error: %s", e)
            raise

        return {
            "session_id": session_id,
            "from_char": from_char,
            "to": to,
            "reply": reply_text,
        }

    def reply(self, session_id: str, from_char: str, say: str, human: bool = False) -> dict:
        """Ajoute un tour à une session existante."""
        from simphonia.services import character_service

        if session_id not in self._sessions:
            raise SessionNotFound(session_id)

        state = self._sessions[session_id]
        if from_char not in state.participants:
            raise InvalidParticipant(from_char, session_id)

        state.history.append(
            DialogueMessage(
                speaker=from_char,
                content=say,
                timestamp=datetime.utcnow(),
            )
        )

        self._log.info(
            "[reply] session=%s from=%r human=%s — %r",
            session_id,
            from_char,
            human,
            say,
        )

        # Déterminer qui répond (l'autre participant)
        responder = state.participants[1] if from_char == state.participants[0] else state.participants[0]
        to_card = character_service.get().get_character(responder)
        to_role = character_service.get().get_type(responder)
        system_prompt = self._build_system_prompt(to_card, responder, from_char, human, to_role, state.scene)
        messages = self._build_messages(state.history, responder, memorize_log=state.memorize_log.get(responder))
        try:
            reply_text = self._call_llm(system_prompt, messages, from_char=responder, state=state)
            state.history.append(DialogueMessage(
                speaker=responder,
                content=reply_text,
                timestamp=datetime.utcnow(),
            ))
            self._log.info("[reply] reply from=%r — %r", responder, reply_text)
            if not human:
                self._dispatch_said(session_id, from_char=responder, to=from_char, content=reply_text)
        except LLMError as e:
            state.history.pop()
            self._log.error("[reply] LLM error — rollback: %s", e)
            raise

        return {"reply": reply_text}

    def auto_reply(self, session_id: str, speaker: str) -> None:
        """Tour autonome : `speaker` (LLM) génère sa réplique, l'autre participant répond."""
        from simphonia.services import character_service

        if session_id not in self._sessions:
            return

        state = self._sessions[session_id]
        other = state.participants[1] if speaker == state.participants[0] else state.participants[0]

        # 1. Générer la réplique de speaker
        try:
            speaker_card = character_service.get().get_character(speaker)
            speaker_role = character_service.get().get_type(speaker)
            sp = self._build_system_prompt(speaker_card, speaker, from_char=other, human=False, role=speaker_role, scene=state.scene)
            msgs = self._build_messages(state.history, speaker, memorize_log=state.memorize_log.get(speaker))
            speaker_say = self._call_llm(sp, msgs, from_char=speaker, state=state)
        except LLMError as e:
            self._log.error("[auto_reply] LLM error générant %r : %s", speaker, e)
            return

        state.history.append(DialogueMessage(speaker=speaker, content=speaker_say, timestamp=datetime.utcnow()))
        self._log.info("[auto_reply] %r — %r", speaker, speaker_say)

        # Publier le message du speaker directement via SSE (pas via le bus,
        # sinon said_command relancerait un auto_reply en boucle)
        self._publish_sse(session_id, from_char=speaker, to=other, content=speaker_say)

        if session_id not in self._sessions:
            return

        # 2. Générer la réponse de other
        try:
            other_card = character_service.get().get_character(other)
            other_role = character_service.get().get_type(other)
            sp2 = self._build_system_prompt(other_card, other, from_char=speaker, human=False, role=other_role, scene=state.scene)
            msgs2 = self._build_messages(state.history, other)
            other_reply = self._call_llm(sp2, msgs2, from_char=other)
        except LLMError as e:
            state.history.pop()
            self._log.error("[auto_reply] LLM error répondant %r : %s", other, e)
            return

        state.history.append(DialogueMessage(speaker=other, content=other_reply, timestamp=datetime.utcnow()))
        self._log.info("[auto_reply] %r — %r", other, other_reply)

        if session_id not in self._sessions:
            return

        # 3. Publier chat.said pour continuer la boucle
        self._dispatch_said(session_id, from_char=other, to=speaker, content=other_reply)

    def stop(self, session_id: str) -> dict:
        """Clôt et supprime la session."""
        if session_id not in self._sessions:
            raise SessionNotFound(session_id)

        self._sessions.pop(session_id)
        self._log.info("[stop] session=%s closed", session_id)
        return {"session_id": session_id, "status": "closed"}

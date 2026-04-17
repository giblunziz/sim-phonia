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
from simphonia.providers.base import LLMProvider
from simphonia.services.chat_service import ChatService
from simphonia.services.chat_service.types import DialogueMessage, DialogueState


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

    def _build_system_prompt(self, to_card: dict, from_char: str, human: bool) -> str:
        fiche = json.dumps(to_card, ensure_ascii=False, indent=2)
        interlocutor = (
            f"Tu parles avec un humain nommé {from_char}."
            if human
            else f"Tu parles avec le personnage {from_char}."
        )
        schema = (
            'Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ni après.\n'
            'Format MVP obligatoire :\n'
            '{"talk": ["Ce que tu dis à voix haute", "plusieurs lignes possibles"]}\n\n'
            'Champs futurs (non requis maintenant) : from, to, actions, mood, inner, '
            'expected, noticed, body, memory'
        )
        return f"Tu es ce personnage :\n{fiche}\n\n{interlocutor}\n\n{schema}"

    def _build_messages(self, history: list[DialogueMessage], to_speaker: str) -> list[dict]:
        messages = []
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
            # Retire la première ligne (``` ou ```json) et la dernière (```)
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

    def _call_llm(self, system_prompt: str, messages: list[dict]) -> str:
        reply_text, stats = self._provider.call(system_prompt, messages)
        if reply_text is None:
            raise LLMError("Le provider LLM n'a retourné aucune réponse")
        try:
            data = json.loads(self._strip_markdown_fences(reply_text))
            talk = data.get("talk", [])
            if isinstance(talk, list) and talk:
                return "\n".join(str(line) for line in talk)
            # talk vide ou absent → fallback
            self._log.warning("Champ 'talk' absent ou vide dans la réponse JSON — fallback texte brut")
            return reply_text.strip()
        except (json.JSONDecodeError, ValueError):
            self._log.warning("Réponse LLM non-JSON — fallback texte brut")
            return reply_text.strip()

    # ------------------------------------------------------------------
    # Interface publique
    # ------------------------------------------------------------------

    def start(self, from_char: str, to: str, say: str, human: bool = False) -> dict:
        """Démarre une nouvelle session de dialogue après validation des participants."""
        from simphonia.services import character_service

        self._validate_character(from_char)
        self._validate_character(to)

        session_id = str(uuid.uuid4())
        state = DialogueState(
            session_id=session_id,
            participants=(from_char, to),
            history=[],
            provider_ref=self._provider_name,
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
        system_prompt = self._build_system_prompt(to_card, from_char, human)
        messages = self._build_messages(state.history, to)
        try:
            reply_text = self._call_llm(system_prompt, messages)
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
        system_prompt = self._build_system_prompt(to_card, from_char, human)
        messages = self._build_messages(state.history, responder)
        try:
            reply_text = self._call_llm(system_prompt, messages)
            state.history.append(DialogueMessage(
                speaker=responder,
                content=reply_text,
                timestamp=datetime.utcnow(),
            ))
            self._log.info("[reply] reply from=%r — %r", responder, reply_text)
            if not human:
                self._dispatch_said(session_id, from_char=responder, to=from_char, content=reply_text)
        except LLMError as e:
            # Rollback : retirer le message de from_char qui vient d'être ajouté
            state.history.pop()
            self._log.error("[reply] LLM error — rollback: %s", e)
            raise

        return {"reply": reply_text}

    def auto_reply(self, session_id: str, speaker: str) -> None:
        """Tour autonome : `speaker` (LLM) génère sa réplique, l'autre participant répond."""
        from simphonia.services import character_service

        if session_id not in self._sessions:
            return  # session stoppée entre temps

        state = self._sessions[session_id]
        other = state.participants[1] if speaker == state.participants[0] else state.participants[0]

        # 1. Générer la réplique de speaker (sa propre fiche, répond à other)
        try:
            speaker_card = character_service.get().get_character(speaker)
            sp = self._build_system_prompt(speaker_card, from_char=other, human=False)
            msgs = self._build_messages(state.history, speaker)
            speaker_say = self._call_llm(sp, msgs)
        except LLMError as e:
            self._log.error("[auto_reply] LLM error générant %r : %s", speaker, e)
            return

        state.history.append(DialogueMessage(speaker=speaker, content=speaker_say, timestamp=datetime.utcnow()))
        self._log.info("[auto_reply] %r — %r", speaker, speaker_say)

        if session_id not in self._sessions:
            return  # stoppée pendant le premier appel LLM

        # 2. Générer la réponse de other
        try:
            other_card = character_service.get().get_character(other)
            sp2 = self._build_system_prompt(other_card, from_char=speaker, human=False)
            msgs2 = self._build_messages(state.history, other)
            other_reply = self._call_llm(sp2, msgs2)
        except LLMError as e:
            state.history.pop()  # rollback speaker_say
            self._log.error("[auto_reply] LLM error répondant %r : %s", other, e)
            return

        state.history.append(DialogueMessage(speaker=other, content=other_reply, timestamp=datetime.utcnow()))
        self._log.info("[auto_reply] %r — %r", other, other_reply)

        if session_id not in self._sessions:
            return  # stoppée pendant le second appel LLM

        # 3. Publier chat.said pour continuer la boucle
        self._dispatch_said(session_id, from_char=other, to=speaker, content=other_reply)

    def stop(self, session_id: str) -> dict:
        """Clôt et supprime la session."""
        if session_id not in self._sessions:
            raise SessionNotFound(session_id)

        self._sessions.pop(session_id)

        self._log.info("[stop] session=%s closed", session_id)

        return {"session_id": session_id, "status": "closed"}

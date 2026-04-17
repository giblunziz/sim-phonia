from simphonia.core import command
from simphonia.services import chat_service

CHAT_BUS = "chat"


@command(bus=CHAT_BUS, code="start", description="Ouvre une session de dialogue entre deux personnages")
def start_command(from_char: str, to: str, say: str, human: bool = False) -> dict:
    return chat_service.get().start(from_char, to, say, human)


@command(bus=CHAT_BUS, code="reply", description="Poursuit une session de dialogue existante")
def reply_command(session_id: str, from_char: str, say: str, human: bool = False) -> dict:
    return chat_service.get().reply(session_id, from_char, say, human)


@command(bus=CHAT_BUS, code="stop", description="Clôt une session de dialogue")
def stop_command(session_id: str) -> dict:
    return chat_service.get().stop(session_id)


@command(bus=CHAT_BUS, code="said", description="Notification: un personnage a pris la parole (LLM → LLM)")
def said_command(session_id: str, from_char: str, to: str, content: str) -> dict:
    import threading

    def _auto():
        try:
            chat_service.get().auto_reply(session_id, speaker=to)
        except Exception as exc:
            import logging
            logging.getLogger("simphonia.chat").warning("[said] auto_reply échoué : %s", exc)

    threading.Thread(target=_auto, daemon=True).start()
    return {"session_id": session_id, "from_char": from_char, "to": to, "received": True}

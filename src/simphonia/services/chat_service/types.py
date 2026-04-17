from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DialogueMessage:
    speaker: str
    content: str
    timestamp: datetime


@dataclass
class DialogueState:
    session_id: str
    participants: tuple[str, str]   # (from_char, to)
    history: list[DialogueMessage] = field(default_factory=list)
    provider_ref: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

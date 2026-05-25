from dataclasses import dataclass
from uuid import uuid4


@dataclass
class ChatSession:
    id: str
    source: str
    repo_name: str
    history: list[dict[str, str]]


class ChatSessionService:
    _sessions: dict[str, ChatSession] = {}

    @classmethod
    def create_session(cls, source: str, repo_name: str) -> ChatSession:
        session = ChatSession(id=str(uuid4()), source=source, repo_name=repo_name, history=[])
        cls._sessions[session.id] = session
        return session

    @classmethod
    def get_session(cls, session_id: str) -> ChatSession | None:
        return cls._sessions.get(session_id)

    @classmethod
    def add_turn(cls, session_id: str, user: str, assistant: str) -> None:
        session = cls._sessions.get(session_id)
        if not session:
            return
        session.history.append({"user": user, "assistant": assistant})

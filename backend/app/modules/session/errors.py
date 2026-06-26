class SessionError(Exception):
    """Base error for session module failures."""


class SessionNotFoundError(SessionError):
    def __init__(self, session_ref: str) -> None:
        super().__init__(f"Session not found: {session_ref}")
        self.session_ref = session_ref

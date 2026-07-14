class GameError(Exception):
    """Base error for game module failures."""


class GameNotFoundError(GameError):
    def __init__(self, room_id: str) -> None:
        super().__init__(f"Game not found for room: {room_id}")
        self.room_id = room_id


class GameNotInProgressError(GameError):
    def __init__(self, room_id: str) -> None:
        super().__init__(f"Game is not in progress for room: {room_id}")
        self.room_id = room_id


class PlayerNotFoundError(GameError):
    def __init__(self, player_id: str) -> None:
        super().__init__(f"Player not found in game: {player_id}")
        self.player_id = player_id


class NotCurrentPlayerError(GameError):
    def __init__(self, player_id: str) -> None:
        super().__init__(f"Player is not current player: {player_id}")
        self.player_id = player_id


class PlayerEliminatedError(GameError):
    def __init__(self, player_id: str) -> None:
        super().__init__(f"Player is eliminated: {player_id}")
        self.player_id = player_id


class PlayerDisconnectedError(GameError):
    def __init__(self, player_id: str) -> None:
        super().__init__(f"Player is disconnected: {player_id}")
        self.player_id = player_id


class InvalidTurnPhaseError(GameError):
    def __init__(self, phase: str) -> None:
        super().__init__(f"Invalid turn phase: {phase}")
        self.phase = phase


class TurnActionLockedError(GameError):
    def __init__(self, room_id: str) -> None:
        super().__init__(f"Turn action is locked for room: {room_id}")
        self.room_id = room_id


class PendingResolutionError(GameError):
    def __init__(self, room_id: str) -> None:
        super().__init__(f"Game has a pending resolution for room: {room_id}")
        self.room_id = room_id


class InvalidPendingDrawsError(GameError):
    def __init__(self, pending_draws: int) -> None:
        super().__init__(f"Invalid pending draws: {pending_draws}")
        self.pending_draws = pending_draws


class EmptyDrawPileError(GameError):
    def __init__(self, room_id: str) -> None:
        super().__init__(f"Draw pile is empty for active game: {room_id}")
        self.room_id = room_id

from enum import StrEnum


class RoomStatus(StrEnum):
    WAITING = "waiting"
    STARTING = "starting"
    IN_GAME = "in_game"
    FINISHED = "finished"


class GamePhase(StrEnum):
    LOBBY = "lobby"
    SETUP = "setup"
    TURN_ACTION = "turn_action"
    TURN_DRAW = "turn_draw"
    RESOLVING_EXPLOSION = "resolving_explosion"
    FINISHED = "finished"


class CardType(StrEnum):
    EXPLODING_KITTEN = "exploding_kitten"
    DEFUSE = "defuse"
    SKIP = "skip"
    ATTACK = "attack"
    SHUFFLE = "shuffle"
    SEE_THE_FUTURE = "see_the_future"
    FAVOR = "favor"


class PlayerStatus(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ELIMINATED = "eliminated"


class ActionType(StrEnum):
    START_GAME = "start_game"
    PLAY_SKIP = "play_skip"
    PLAY_ATTACK = "play_attack"
    PLAY_SHUFFLE = "play_shuffle"
    PLAY_SEE_THE_FUTURE = "play_see_the_future"
    PLAY_FAVOR = "play_favor"
    DRAW_CARD = "draw_card"
    DEFUSE = "defuse"
    EXPLODE = "explode"
    ELIMINATE = "eliminate"
    TURN_ADVANCED = "turn_advanced"

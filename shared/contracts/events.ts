import type * as Request from "./requests";
import type * as Response from "./responses";

type Ack = (response?: Response.BootstrapResponse | null) => void;
export interface ClientToServerEvents {
  "room:create": (payload: Request.RoomCreateRequest, ack: Ack) => void;
  "room:join": (payload: Request.RoomJoinRequest, ack: Ack) => void;
  "player:reconnect": (payload: Request.ReconnectRequest, ack: Ack) => void;
  "room:ready": (payload: Request.RoomReadyRequest) => void;
  "game:start": (payload: Request.GameStartRequest) => void;
  "turn:play-card": (payload: Request.PlayCardRequest) => void;
  "turn:draw-card": (payload: Request.DrawCardRequest) => void;
}
export interface ServerToClientEvents {
  "system:connected": (payload: Response.SystemConnectedEvent) => void;
  "room:updated": (payload: Response.RoomUpdatedEvent) => void;
  "game:started": (payload: Response.GameStartedEvent) => void;
  "turn:started": (payload: Response.TurnStartedEvent) => void;
  "game:state": (payload: Response.PublicGameStateEvent) => void;
  "player:private-state": (payload: Response.PlayerPrivateStateEvent) => void;
  "player:eliminated": (payload: Response.PlayerEliminatedEvent) => void;
  "game:ended": (payload: Response.GameEndedEvent) => void;
  "session:replaced": (payload: Response.SessionReplacedEvent) => void;
  "error": (payload: Response.ErrorEvent) => void;
}

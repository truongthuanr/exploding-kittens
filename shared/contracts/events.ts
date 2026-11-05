import type * as Request from "./requests";
import type * as Response from "./responses";

type Ack = (response?: Response.BootstrapResponse | null) => void;
type RestoreAck = (response?: Response.BootstrapResponse | Response.RoomLeftRestoreResponse | null) => void;
type GameActionAck = (response?: Response.GameActionAck | null) => void;
type RematchVoteAck = (response?: Response.RematchVoteAck | null) => void;
type LeaveRoomAck = (response?: Response.LeaveRoomAck | null) => void;
export interface ClientToServerEvents {
  "room:create": (payload: Request.RoomCreateRequest, ack: Ack) => void;
  "room:join": (payload: Request.RoomJoinRequest, ack: Ack) => void;
  "player:reconnect": (payload: Request.ReconnectRequest, ack: RestoreAck) => void;
  "room:ready": (payload: Request.RoomReadyRequest) => void;
  "room:rematch-ready": (payload: Request.RematchReadyRequest, ack: RematchVoteAck) => void;
  "room:rematch-withdraw": (payload: Request.RematchWithdrawRequest, ack: RematchVoteAck) => void;
  "room:leave": (payload: Request.LeaveRoomRequest, ack: LeaveRoomAck) => void;
  "game:start": (payload: Request.GameStartRequest) => void;
  "turn:play-card": (payload: Request.PlayCardRequest, ack?: GameActionAck) => void;
  "turn:draw-card": (payload: Request.DrawCardRequest, ack?: GameActionAck) => void;
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

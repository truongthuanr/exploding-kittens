import { describe, expect, it } from "vitest";
import { describeRealtimeError } from "../lib/socket/error-messages";

describe("describeRealtimeError", () => {
  it("tells users to discard terminal admission requests before changing inputs", () => {
    for (const code of ["room_not_found", "duplicate_nickname", "room_full", "room_not_joinable",
      "request_expired", "server_restarted", "request_conflict", "invalid_request_id", "invalid_payload"]) {
      const result = describeRealtimeError({ code, message: "Internal backend detail" }, "join_failed");
      expect(result.action, code).toBe("discard_admission");
      expect(result.message, code).not.toContain("Internal backend detail");
    }
  });

  it("retries an uncertain admission with the same request", () => {
    expect(describeRealtimeError({ code: "timeout", message: "raw" }, "join_failed")).toMatchObject({
      action: "retry_admission",
    });
    expect(describeRealtimeError({ code: "invalid_ack", message: "raw" }, "join_failed").message)
      .toContain("cùng yêu cầu");
    expect(describeRealtimeError({ code: "admission_busy", message: "raw" }, "join_failed").action)
      .toBe("retry_admission");
  });

  it("routes restore and takeover errors to the right recovery action", () => {
    expect(describeRealtimeError({ code: "timeout", message: "raw" }, "restore_failed").action)
      .toBe("retry_restore");
    expect(describeRealtimeError({ code: "session_in_use", message: "raw" }, "replaced").action)
      .toBe("take_over");
    expect(describeRealtimeError({ code: "invalid_session", message: "raw" }, "invalid").action)
      .toBeNull();
  });

  it("uses concise lobby messages and a safe fallback for unknown codes", () => {
    expect(describeRealtimeError({ code: "players_not_ready", message: "raw" }, "ready").message)
      .toContain("Ready");
    const unknown = describeRealtimeError({ code: "unexpected", message: "Secret server path" }, "ready");
    expect(unknown.message).not.toContain("Secret server path");
    expect(unknown.action).toBeNull();
  });
});

import { test, expect, type Page } from "@playwright/test";
async function connected(page: Page) {
  await page.goto("/"); await expect(page.getByTestId("connection")).toHaveText("connected");
}
async function create(page: Page, name: string) {
  await connected(page); await page.getByLabel("Nickname", { exact: true }).fill(name);
  await page.getByRole("button", { name: "Create room", exact: true }).click();
  await expect(page.getByTestId("session")).toHaveText("ready");
  return (await page.getByTestId("room-code").textContent())!;
}
async function snapshot(page: Page, name: string) { return JSON.parse((await page.getByTestId(name).textContent())!); }

test("create/join, lobby reload, game bootstrap and private hand survive reload", async ({ browser }) => {
  const contexts = await Promise.all([browser.newContext(), browser.newContext(), browser.newContext()]);
  try {
    const pages = await Promise.all(contexts.map(context => context.newPage()));
    const errors: string[] = []; pages.forEach(page => page.on("pageerror", error => errors.push(error.message)));
    const code = await create(pages[0], "Host");
    const identity = await pages[0].getByTestId("player-id").textContent();
    await pages[0].reload(); await expect(pages[0].getByTestId("session")).toHaveText("ready");
    await expect(pages[0].getByTestId("player-id")).toHaveText(identity!);
    for (let i = 1; i < 3; i++) {
      await connected(pages[i]); await pages[i].getByLabel("Nickname", { exact: true }).fill(`Player ${i}`);
      await pages[i].getByLabel("Room code", { exact: true }).fill(code);
      await pages[i].getByRole("button", { name: "Join room", exact: true }).click();
      await expect(pages[i].getByTestId("session")).toHaveText("ready");
    }
    for (const page of pages) await page.getByRole("button", { name: "Ready", exact: true }).click();
    await expect.poll(async () => (await snapshot(pages[0], "room-state")).players.every((p: { isReady: boolean }) => p.isReady)).toBe(true);
    await pages[0].getByRole("button", { name: "Start game", exact: true }).click();
    for (const page of pages) await expect(page.getByTestId("private-state")).toContainText("cardId");
    const hand = (await snapshot(pages[0], "private-state")).hand;
    const otherHand = (await snapshot(pages[1], "private-state")).hand;
    expect(hand.map((c: { cardId: string }) => c.cardId)).not.toEqual(otherHand.map((c: { cardId: string }) => c.cardId));
    await pages[0].reload(); await expect(pages[0].getByTestId("session")).toHaveText("ready");
    expect((await snapshot(pages[0], "private-state")).hand).toEqual(hand);
    expect(await pages[0].getByTestId("game-state").textContent()).not.toContain("cardId");
    const game = await snapshot(pages[0], "game-state"), privateState = await snapshot(pages[0], "private-state");
    expect(game.stateVersion).toBe(privateState.stateVersion);
    const storage = await pages[0].evaluate(() => localStorage.getItem("boardgame.identity.v1"));
    expect(storage).not.toContain("hand"); expect(errors).toEqual([]);
  } finally { await Promise.all(contexts.map(context => context.close())); }
});

test("new tab requires explicit takeover and old tab stays replaced", async ({ context, page }) => {
  await create(page, "Owner"); const player = await page.getByTestId("player-id").textContent();
  const other = await context.newPage(); await other.goto("/");
  await expect(other.getByTestId("session")).toHaveText("replaced");
  await expect(page.getByTestId("session")).toHaveText("ready");
  await other.getByRole("button", { name: "Tiếp tục ở tab này" }).click();
  await expect(other.getByTestId("session")).toHaveText("ready");
  await expect(page.getByTestId("session")).toHaveText("replaced");
  await expect(other.getByTestId("player-id")).toHaveText(player!);
  await expect(page.getByRole("button", { name: "Ready", exact: true })).toBeDisabled();
  expect(await other.evaluate(() => localStorage.getItem("boardgame.identity.v1"))).not.toBeNull();
});

test("offline owner cannot reclaim after another instance takes over", async ({ browser }) => {
  const first = await browser.newContext(), second = await browser.newContext();
  try {
    const a = await first.newPage(); await create(a, "Offline owner");
    const identity = await a.evaluate(() => localStorage.getItem("boardgame.identity.v1"));
    await second.addInitScript(value => localStorage.setItem("boardgame.identity.v1", value!), identity);
    await first.setOffline(true);
    await expect(a.getByTestId("connection")).not.toHaveText("connected", { timeout: 50000 });
    const b = await second.newPage(); await b.goto("/");
    await expect(b.getByTestId("session")).toHaveText("replaced");
    await b.getByRole("button", { name: "Tiếp tục ở tab này" }).click();
    await expect(b.getByTestId("session")).toHaveText("ready");
    await first.setOffline(false);
    await expect(a.getByTestId("session")).toHaveText("replaced", { timeout: 30000 });
    await expect(b.getByTestId("session")).toHaveText("ready");
  } finally { await first.close(); await second.close(); }
});

test("unknown stored session exits restore and permits a new admission", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("boardgame.identity.v1", JSON.stringify({ version: 1, roomId: "gone", roomCode: "GONE", playerId: "gone", playerSessionId: "gone" })));
  await connected(page); await expect(page.getByTestId("session")).toHaveText("invalid");
  expect(await page.evaluate(() => localStorage.getItem("boardgame.identity.v1"))).toBeNull();
  await page.getByLabel("Nickname", { exact: true }).fill("New session");
  await page.getByRole("button", { name: "Create room", exact: true }).click();
  await expect(page.getByTestId("session")).toHaveText("ready");
});

test("lost create ack is recovered after reload without a duplicate seat", async ({ page }) => {
  let dropAck = true, upgraded = false, discarded = false;
  await page.routeWebSocket(/\/socket\.io\//, route => {
    const server = route.connectToServer();
    route.onMessage(message => { if (message === "5") upgraded = true; server.send(message); });
    server.onMessage(message => {
      if (dropAck && typeof message === "string" && /^43\d+\[/.test(message)) {
        dropAck = false; discarded = true; return;
      }
      route.send(message);
    });
  });
  await connected(page);
  await expect.poll(() => upgraded).toBe(true);
  await page.getByLabel("Nickname", { exact: true }).fill("Lost ack");
  await page.getByRole("button", { name: "Create room", exact: true }).click();
  await expect.poll(() => discarded).toBe(true);
  await expect(page.getByTestId("session")).toHaveText("join_failed", { timeout: 15000 });
  const request = await page.evaluate(() => JSON.parse(sessionStorage.getItem("boardgame.pending.v1")!));
  await page.reload(); await expect(page.getByTestId("connection")).toHaveText("connected");
  expect((await page.evaluate(() => JSON.parse(sessionStorage.getItem("boardgame.pending.v1")!))).payload.requestId).toBe(request.payload.requestId);
  await page.getByRole("button", { name: "Retry admission", exact: true }).click();
  // If the old connection hasn't been observed closed, replay recovers identity but requires explicit takeover.
  await expect.poll(async () => page.getByTestId("session").textContent()).toMatch(/^(ready|replaced)$/);
  if (await page.getByTestId("session").textContent() === "replaced") {
    await page.getByRole("button", { name: "Tiếp tục ở tab này" }).click();
  }
  await expect(page.getByTestId("session")).toHaveText("ready");
  expect((await snapshot(page, "room-state")).players).toHaveLength(1);
  expect(await page.evaluate(() => sessionStorage.getItem("boardgame.pending.v1"))).toBeNull();
});

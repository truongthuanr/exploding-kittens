import { test, expect, type Page } from "@playwright/test";

async function connected(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("connection")).toHaveText("connected");
}

async function create(page: Page, name: string) {
  await connected(page);
  await page.getByLabel("Nickname", { exact: true }).fill(name);
  await page.getByRole("button", { name: "Create room", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Room [A-Z0-9]+/ })).toBeVisible();
  return (await page.getByTestId("room-code").textContent())!;
}

async function join(page: Page, name: string, code: string) {
  await connected(page);
  await page.getByLabel("Nickname", { exact: true }).fill(name);
  await page.getByLabel("Room code", { exact: true }).fill(code);
  await page.getByRole("button", { name: "Join room", exact: true }).click();
  await expect(page.getByTestId("room-code")).toHaveText(code);
}

test("three players create, join, ready, start, and restore into the game boundary", async ({ browser }) => {
  const contexts = await Promise.all([browser.newContext(), browser.newContext(), browser.newContext()]);
  try {
    const pages = await Promise.all(contexts.map(context => context.newPage()));
    const errors: string[] = [];
    pages.forEach(page => page.on("pageerror", error => errors.push(error.message)));
    const code = await create(pages[0], "Host");
    await expect(pages[0].getByRole("button", { name: "Start game" })).toBeDisabled();
    await join(pages[1], "Bob", code);
    await join(pages[2], "Cat", code);
    for (const page of pages) {
      await expect(page.locator(".player")).toHaveCount(3);
      await page.getByRole("button", { name: "Ready", exact: true }).click();
    }
    await expect(pages[1].getByRole("button", { name: "Start game" })).toHaveCount(0);
    await expect(pages[0].getByRole("button", { name: "Start game" })).toBeEnabled();
    await pages[0].getByRole("button", { name: "Start game" }).click();
    for (const page of pages) await expect(page.getByRole("heading", { name: "Trận đấu đã bắt đầu" })).toBeVisible();
    await pages[0].reload();
    await expect(pages[0].getByRole("heading", { name: "Trận đấu đã bắt đầu" })).toBeVisible();
    expect(await pages[0].evaluate(() => localStorage.getItem("boardgame.identity.v1"))).not.toContain("hand");
    expect(errors).toEqual([]);
  } finally { await Promise.all(contexts.map(context => context.close())); }
});

test("new tab requires explicit takeover and old tab shows recovery", async ({ context, page }) => {
  const code = await create(page, "Owner");
  const other = await context.newPage();
  await other.goto("/");
  await expect(other.getByRole("heading", { name: "Phiên đang hoạt động ở tab khác" })).toBeVisible();
  await other.getByRole("button", { name: "Tiếp tục ở tab này" }).click();
  await expect(other.getByTestId("room-code")).toHaveText(code);
  await expect(page.getByRole("heading", { name: "Phiên đang hoạt động ở tab khác" })).toBeVisible();
});

test("invalid saved session returns to Home and permits a new room", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("boardgame.identity.v1", JSON.stringify({
    version: 1, roomId: "gone", roomCode: "GONE", playerId: "gone", playerSessionId: "gone",
  })));
  await connected(page);
  await expect(page.getByText("Phiên trước không còn hợp lệ.")).toBeVisible();
  await page.getByLabel("Nickname", { exact: true }).fill("New session");
  await page.getByRole("button", { name: "Create room", exact: true }).click();
  await expect(page.getByTestId("room-code")).toBeVisible();
});

test("saved session conflict requires an explicit decision", async ({ page }) => {
  const code = await create(page, "Owner");
  await page.evaluate(() => sessionStorage.setItem("boardgame.pending.v1", JSON.stringify({
    event: "room:create", createdAt: Date.now(), expiresAt: Date.now() + 120000,
    payload: { nickname: "Pending", clientInstanceId: "instance", requestId: "pending-request" },
  })));
  await page.reload();
  await expect(page.getByRole("heading", { name: "Xung đột phiên" })).toBeVisible();
  await expect(page.getByTestId("room-code")).toHaveCount(0);
  await page.getByRole("button", { name: "Tiếp tục phiên đã lưu" }).click();
  await expect(page.getByTestId("room-code")).toHaveText(code);
  expect(await page.evaluate(() => sessionStorage.getItem("boardgame.pending.v1"))).toBeNull();
});

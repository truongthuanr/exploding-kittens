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
  await page.getByRole("radio", { name: "Vào phòng" }).check();
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
    await expect(pages[0].getByRole("button", { name: "Start game" })).toBeDisabled();
    await expect(pages[0].getByText("Cần từ 3 đến 5 người chơi.")).toBeVisible();
    await join(pages[2], "Cat", code);
    for (const page of pages) await expect(page.locator(".player")).toHaveCount(3);
    await pages[1].reload();
    await expect(pages[1].getByTestId("room-code")).toHaveText(code);
    await pages[0].getByRole("button", { name: "Ready", exact: true }).click();
    await pages[1].getByRole("button", { name: "Ready", exact: true }).click();
    for (const page of pages) {
      await expect(page.locator(".player .badge").filter({ hasText: /^Ready$/ })).toHaveCount(2);
    }
    await expect(pages[0].getByRole("button", { name: "Start game" })).toBeDisabled();
    await expect(pages[0].getByText("Tất cả người chơi cần Ready.")).toBeVisible();
    await pages[2].getByRole("button", { name: "Ready", exact: true }).click();
    for (const page of pages) await expect(page.locator(".player .badge").filter({ hasText: /^Ready$/ })).toHaveCount(3);
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

test("Home validates the selected form and submits with Enter", async ({ browser }) => {
  const hostContext = await browser.newContext(), guestContext = await browser.newContext();
  try {
    const host = await hostContext.newPage(), guest = await guestContext.newPage();
    await connected(host);
    await host.getByLabel("Nickname", { exact: true }).focus();
    await host.keyboard.press("Enter");
    await expect(host.locator("#nickname")).toBeFocused();
    await expect(host.locator("#nickname")).toHaveAttribute("aria-invalid", "true");
    await expect(host.locator("#nickname-error")).toHaveText("Nhập tên người chơi.");
    await host.getByLabel("Nickname", { exact: true }).fill("Keyboard host");
    await host.getByLabel("Nickname", { exact: true }).press("Enter");
    const code = await host.getByTestId("room-code").textContent();

    await connected(guest);
    await guest.getByRole("radio", { name: "Vào phòng" }).check();
    await guest.getByLabel("Nickname", { exact: true }).fill("Keyboard guest");
    await guest.getByLabel("Nickname", { exact: true }).press("Enter");
    await expect(guest.locator("#room-code-input")).toBeFocused();
    await expect(guest.locator("#room-code-input")).toHaveAttribute("aria-invalid", "true");
    await guest.getByLabel("Room code", { exact: true }).fill(code!);
    await guest.getByLabel("Room code", { exact: true }).press("Enter");
    await expect(guest.getByTestId("room-code")).toHaveText(code!);
  } finally { await hostContext.close(); await guestContext.close(); }
});

test("a disconnected player blocks Start until that player restores the Lobby", async ({ browser }) => {
  const contexts = await Promise.all([browser.newContext(), browser.newContext(), browser.newContext()]);
  try {
    const pages = await Promise.all(contexts.map(context => context.newPage()));
    const code = await create(pages[0], "Host");
    await join(pages[1], "Bob", code);
    await join(pages[2], "Cat", code);
    for (const page of pages) await page.getByRole("button", { name: "Ready", exact: true }).click();
    await expect(pages[0].getByRole("button", { name: "Start game" })).toBeEnabled();
    await pages[2].close();
    await expect(pages[0].getByRole("button", { name: "Start game" })).toBeDisabled();
    await expect(pages[0].getByText("Tất cả người chơi cần kết nối.")).toBeVisible();
    const restored = await contexts[2].newPage();
    await restored.goto("/");
    await expect(restored.getByRole("heading", { name: "Phiên đang hoạt động ở tab khác" })).toBeVisible();
    await restored.getByRole("button", { name: "Tiếp tục ở tab này" }).click();
    await expect(restored.getByTestId("room-code")).toHaveText(code);
    await expect(pages[0].getByRole("button", { name: "Start game" })).toBeEnabled();
  } finally { await Promise.all(contexts.map(context => context.close())); }
});

test("Home and Lobby fit mobile and desktop and expose keyboard focus", async ({ page }) => {
  for (const width of [320, 375, 1280]) {
    await page.setViewportSize({ width, height: 800 });
    await connected(page);
    await expect(page.getByRole("heading", { name: "Chơi cùng bạn bè" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.keyboard.press("Tab");
    await expect(page.getByRole("radio", { name: "Tạo phòng" })).toBeFocused();
    expect(await page.getByRole("radio", { name: "Tạo phòng" }).evaluate(el => getComputedStyle(el).outlineStyle)).not.toBe("none");
  }
  await page.getByLabel("Nickname", { exact: true }).fill("A long player nickname for responsive layout");
  await page.getByRole("button", { name: "Create room" }).click();
  await expect(page.getByTestId("room-code")).toBeVisible();
  for (const width of [320, 375, 1280]) {
    await page.setViewportSize({ width, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await expect(page.getByRole("button", { name: "Start game" })).toBeDisabled();
    await expect(page.getByText("Cần từ 3 đến 5 người chơi.")).toBeVisible();
  }
  const contrasts = await page.evaluate(() => {
    const rgb = (value: string) => value.match(/\d+/g)!.slice(0, 3).map(Number);
    const luminance = (color: number[]) => color.map(channel => {
      const c = channel / 255;
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    }).reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0);
    const ratio = (foreground: string, background: string) => {
      const [light, dark] = [luminance(rgb(foreground)), luminance(rgb(background))].sort((a, b) => b - a);
      return (light + 0.05) / (dark + 0.05);
    };
    const panel = document.querySelector(".panel")!;
    const surface = getComputedStyle(panel).backgroundColor;
    return ["h1", ".requirements", ".badge", "button:not(:disabled)"].map(selector => {
      const element = document.querySelector(selector)!;
      const style = getComputedStyle(element);
      const background = selector === ".badge" || selector.startsWith("button") ? style.backgroundColor : surface;
      return { selector, ratio: ratio(style.color, background) };
    });
  });
  for (const item of contrasts) expect(item.ratio, item.selector).toBeGreaterThanOrEqual(4.5);
});

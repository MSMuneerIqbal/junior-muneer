import { expect, test } from "@playwright/test";

test.afterEach(async ({ request }) => {
  await request.put("http://127.0.0.1:8100/api/computer/desktop", { data: { enabled: false, apps: ["notepad.exe"] } });
  await request.put("http://127.0.0.1:8100/api/permissions/rules/computer.desktop.input", { data: { rule: "ask" } });
});

test("desktop opt-in, preview and reviewed typing use the simulated adapter", async ({ page }, info) => {
  test.setTimeout(75_000);
  await page.goto("/settings#computer");
  const desktop = page.getByRole("region", { name: "Desktop controls", exact: true });
  const toggle = desktop.getByRole("checkbox", { name: "Enable desktop controls" });
  await expect(toggle).not.toBeChecked();
  await toggle.check();
  const allApps = desktop.getByRole("checkbox", { name: "Allow other app windows" });
  await allApps.check();
  await expect(allApps).toBeChecked();
  await allApps.uncheck();
  await expect(allApps).not.toBeChecked();
  await desktop.getByRole("button", { name: "Refresh app windows" }).click();
  await desktop.getByRole("button", { name: "Preview Junior desktop demo" }).click();
  await expect(desktop.getByRole("img", { name: "Desktop preview: Junior desktop demo" })).toBeVisible();
  const marker = `desktop-note-${info.project.name}-${Date.now()}`;
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill(`pc desktop type ${marker}`);
  await box.press("Enter");
  const card = page.getByRole("article").filter({ hasText: marker });
  await expect(card.getByTestId("approval-status")).toHaveText("Waiting for you", { timeout: 30_000 });
  await expect(card.getByRole("img", { name: "Window observed for the desktop approval" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Read aloud" })).toBeVisible();
  await card.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(card.getByRole("textbox", { name: "Edit draft" })).toHaveValue(marker);
  await card.getByRole("textbox", { name: "Edit draft" }).fill(`${marker} edited`);
  await card.getByRole("button", { name: "Save", exact: true }).click();
  await expect(card.getByText(`${marker} edited`, { exact: true })).toBeVisible();
  await card.getByRole("button", { name: "Approve & run" }).click();
  await expect(card.getByTestId("approval-status")).toHaveText("Done");
  await page.goto("/settings#computer");
  await desktop.getByRole("button", { name: "Refresh app windows" }).click();
  await desktop.getByRole("button", { name: "Preview Junior desktop demo" }).click();
  await expect(desktop.getByRole("img")).toBeVisible();
  await toggle.uncheck();
  await expect(toggle).not.toBeChecked();
});

test("Junior closes a user-requested app in Auto", async ({ page, request }) => {
  test.setTimeout(75_000);
  await request.put("http://127.0.0.1:8100/api/computer/desktop", { data: { enabled: true, apps: ["notepad.exe"] } });
  await request.put("http://127.0.0.1:8100/api/permissions/rules/computer.desktop.input", { data: { rule: "auto" } });
  await request.put("http://127.0.0.1:8100/api/permissions/mode", { data: { mode: "rules" } });
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill("pc desktop close Notepad");
  await box.press("Enter");
  const card = page.getByRole("article").filter({ hasText: "Close in Notepad" });
  await expect(card.getByTestId("approval-status")).toHaveText("Done", { timeout: 30_000 });
});

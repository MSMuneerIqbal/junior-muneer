import { expect, test } from "@playwright/test";

test.afterEach(async ({ request }) => {
  await request.put("http://127.0.0.1:8100/api/computer/browser", { data: { enabled: false, sites: [] } });
  await request.put("http://127.0.0.1:8100/api/permissions/mode", { data: { mode: "rules" } });
});

test("allow all public websites can be switched on and off", async ({ page }, info) => {
  await page.goto("/settings#computer");
  const browser = page.getByRole("region", { name: "Browser controls", exact: true });
  const all = browser.getByRole("checkbox", { name: "Allow all public websites" });
  await all.check();
  await expect(all).toBeChecked();
  await expect(browser.getByRole("textbox", { name: "Allowed website origins (one per line)" })).toHaveCount(0);
  await browser.screenshot({ path: `test-results/browser-all-${info.project.name}.png` });
  await page.reload();
  await expect(all).toBeChecked();
  await all.uncheck();
  await expect(browser.getByRole("textbox", { name: "Allowed website origins (one per line)" })).toBeVisible();
});

test("explicit local debugging connection shows attachment and disconnects", async ({ page, request }) => {
  await request.put("http://127.0.0.1:8100/api/computer/browser", { data: { enabled: true, sites: ["https://example.com"] } });
  await page.goto("/settings#computer");
  const browser = page.getByRole("region", { name: "Browser controls", exact: true });
  await browser.getByText("Optional: connect a separate debugging browser", { exact: true }).click();
  await browser.getByRole("spinbutton", { name: "Local debugging port" }).fill("9222");
  await browser.getByRole("button", { name: "Connect debugging browser", exact: true }).click();
  await expect(browser.getByRole("status")).toHaveText("Debugging browser attached · 127.0.0.1:9222");
  await expect(browser.getByText(/Ask Junior to open an allowed website/)).toBeVisible();
  await browser.getByRole("button", { name: "Disconnect browser", exact: true }).click();
  await expect(browser.getByRole("status")).toContainText("Ready — no page open yet");
});

test("browser scope, reviewed navigation, page preview and disconnect", async ({ page, request }, info) => {
  test.setTimeout(75_000);
  await request.put("http://127.0.0.1:8100/api/permissions/mode", { data: { mode: "ask_all" } });
  await page.goto("/settings#computer");
  const browser = page.getByRole("region", { name: "Browser controls", exact: true });
  const toggle = browser.getByRole("checkbox", { name: "Enable browser controls" });
  await expect(toggle).not.toBeChecked();
  await browser.getByRole("textbox", { name: "Allowed website origins (one per line)" }).fill("http://127.0.0.1");
  await browser.getByRole("button", { name: "Save websites" }).click();
  await expect(browser.getByRole("alert")).toBeVisible();
  await browser.getByRole("textbox").fill("https://example.com");
  await browser.getByRole("button", { name: "Save websites" }).click();
  await expect(browser.getByRole("alert")).toHaveCount(0);
  await toggle.check();
  await expect(browser.getByRole("status")).toContainText("Ready — no page open yet");
  const url = `https://example.com/research-${info.project.name}-${Date.now()}`;
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill(`pc browse ${url}`);
  await box.press("Enter");
  const card = page.getByRole("article").filter({ hasText: url });
  await expect(card.getByTestId("approval-status")).toHaveText("Waiting for you", { timeout: 30_000 });
  await expect(card.getByRole("button", { name: "Edit", exact: true })).toBeDisabled();
  await card.getByRole("button", { name: "Approve & run" }).click();
  await expect(card.getByTestId("approval-status")).toHaveText("Done");
  await expect(card).toContainText("has not been read yet");
  await expect(page.getByRole("button", { name: "Read aloud" })).toHaveCount(1);
  const marker = `browser-note-${info.project.name}-${Date.now()}`;
  await box.fill(`pc browser fill ${marker}`);
  await box.press("Enter");
  const fill = page.getByRole("article").filter({ hasText: marker });
  await expect(fill.getByTestId("approval-status")).toHaveText("Waiting for you", { timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Read aloud" })).toHaveCount(2);
  await fill.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(fill.getByRole("textbox", { name: "Edit draft" })).toHaveValue(marker);
  await fill.getByRole("textbox", { name: "Edit draft" }).fill(`${marker} edited`);
  await fill.getByRole("button", { name: "Save", exact: true }).click();
  await fill.getByRole("button", { name: "Approve & run" }).click();
  await expect(fill.getByTestId("approval-status")).toHaveText("Done");
  await page.goto("/settings#computer");
  await expect(browser.getByRole("status")).toContainText(url);
  await browser.getByRole("button", { name: "Preview page" }).click();
  await expect(browser.getByText("Simulated research page", { exact: true })).toBeVisible();
  await expect(browser.getByText(`${marker} edited`, { exact: true })).toBeVisible();
  await browser.getByRole("button", { name: "Disconnect browser", exact: true }).click();
  await expect(browser.getByRole("status")).toContainText("Ready — no page open yet");
});

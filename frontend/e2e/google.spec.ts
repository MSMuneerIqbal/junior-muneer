import { expect, test } from "@playwright/test";

test("Connect Google goes to Google's consent page and back, connected", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "one shared database: once is enough");
  await page.goto("/settings#connections");
  const connect = page.getByRole("link", { name: "Connect Google" });
  await expect(connect).toBeVisible();
  await connect.click(); // the pretend Google approves at once and sends you back
  await expect(page.getByRole("status").filter({ hasText: "Connected as you@example.com." })).toBeVisible();
  await expect(page.getByText("Connected as you@example.com", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/settings#connections$/);
});

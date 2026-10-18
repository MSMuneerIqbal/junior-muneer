import { expect, test } from "@playwright/test";

test("📎 attaches a file: its tag goes into the message", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("File to attach").setInputFiles({ name: "My CV.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7 cv") });
  const box = page.getByRole("textbox", { name: "Message" });
  await expect(box).toHaveValue(/^\[file \d+: My CV\.pdf \(PDF, 1 KB\)\]\n$/);
  await expect(box).toBeFocused();
});

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

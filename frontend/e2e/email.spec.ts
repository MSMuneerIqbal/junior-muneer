import { expect, test } from "@playwright/test";

test("asking in chat emails it to your own Gmail", async ({ page }) => {
  const tag = Date.now().toString(36);
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill(`email me today's plan ${tag}`);
  await box.press("Enter");
  // The pretend Gmail (e2e backend) keeps it on this PC.
  await expect(page.getByText(/Tool said: Sent to me@example\.com/)).toBeVisible({ timeout: 20_000 });
});

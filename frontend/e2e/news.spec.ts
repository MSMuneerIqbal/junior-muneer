import { expect, test } from "@playwright/test";

test("AI and Pakistan news questions go to the news agents, with their steps in Show work", async ({ page }) => {
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });

  await box.fill("What's the latest AI news?");
  await box.press("Enter");
  // The first question builds today's digest first.
  await expect(page.getByText(/From today's digest: Introducing GPT-7 \(sample/)).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "▸ Show work" }).click();
  await expect(page.getByText("Asking the AI-News-Agent")).toBeVisible();
  await expect(page.getByText(/official sources/).first()).toBeVisible();

  await box.fill("What's trending in Pakistan news?");
  await box.press("Enter");
  await expect(page.getByText(/From today's digest: babar azam/)).toBeVisible();
});

import { expect, test } from "@playwright/test";

test("“What happened today?” is answered from the app's records", async ({ page }, info) => {
  const tag = `${info.project.name}-${Date.now().toString(36)}`;
  await page.goto("/");
  await page.getByRole("textbox", { name: "Message" }).fill(`draft A post about ${tag}`);
  await page.getByRole("textbox", { name: "Message" }).press("Enter");
  await expect(page.getByRole("article", { name: new RegExp(tag) })).toBeVisible({ timeout: 15_000 });

  await page.goto("/");
  await page.getByRole("textbox", { name: "Message" }).fill("What happened today?");
  await page.getByRole("textbox", { name: "Message" }).press("Enter");
  const answer = page.getByText("(fake AI) Here's your day:").locator("xpath=ancestor::div[contains(@class,'prose-chat')]");
  await expect(answer).toContainText("What happened: today", { timeout: 15_000 });
  await expect(answer).toContainText("Drafts and posting");
  await expect(answer).toContainText("Waiting for your OK right now");
  await page.getByRole("button", { name: "▸ Show work" }).last().click();
  await expect(page.getByText("Checking what happened")).toBeVisible();
});

test("the morning briefing: made once a day, opened from the Today panel", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "the Today panel is beside the chat on wide screens");
  await page.goto("/");
  const link = page.getByRole("link", { name: "Today's briefing", exact: true });
  if (!(await link.isVisible())) {
    await page.getByRole("button", { name: "☀ Today's briefing" }).click();
  }
  await expect(link).toBeVisible({ timeout: 15_000 });
  await link.click();
  await expect(page.getByText(/\(fake AI\) Good morning!/)).toBeVisible();
  await expect(page.getByRole("link", { name: /☀ Morning briefing · / }).first()).toBeVisible(); // in your chat list
});

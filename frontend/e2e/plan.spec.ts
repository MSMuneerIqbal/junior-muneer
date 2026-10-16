import { expect, test } from "@playwright/test";

test("a request with several parts shows a checklist that gets ticked off, and stays after a reload", async ({ page }, info) => {
  const tag = `${info.project.name}-${Date.now().toString(36)}`;
  await page.goto("/");
  await page.getByRole("textbox", { name: "Message" }).fill(`do these: LinkedIn post ${tag}; reply to Sam; AI news`);
  await page.getByRole("textbox", { name: "Message" }).press("Enter");

  const plan = page.getByRole("region", { name: "Plan" }).last();
  await expect(plan).toContainText("Plan: 3 of 3 done", { timeout: 15_000 });
  await expect(plan.getByRole("listitem")).toHaveCount(3);
  await expect(plan.getByRole("listitem").first()).toContainText(`LinkedIn post ${tag}`);
  await expect(plan.locator('li[data-status="done"]')).toHaveCount(3);
  await expect(page.getByText("(fake AI) All 3 parts done.")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("region", { name: "Plan" }).last()).toContainText("Plan: 3 of 3 done");
});


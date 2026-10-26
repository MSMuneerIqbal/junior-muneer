import { expect, test } from "@playwright/test";

test("Code changes require reviewed tests, separate apply and explicit rollback", async ({ page }, info) => {
  test.setTimeout(180_000); // three reviewed operations and cold Windows subprocess/import startup
  await page.goto("/");
  const message = page.getByRole("textbox", { name: "Message" });
  await message.fill("propose code fix the demo square function");
  await message.press("Enter");
  await expect(page.getByText(/Staged proposal [0-9a-f]{32}/).last()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Native tests can do anything your account can", { exact: false }).first()).toBeVisible();
  await page.getByRole("button", { name: "Approve & test", exact: true }).click();
  await expect(page.getByText(/Passed: Backend tests/).first()).toBeVisible({ timeout: 30_000 });
  await page.goto("/settings#advanced");
  const group = page.getByRole("group", { name: "Code proposals" });
  const proposal = group.getByRole("article").first();
  await expect(proposal).toContainText("passed:", { timeout: 15_000 });
  await proposal.getByText("Review full diff").click();
  await expect(proposal).toContainText("return n * n");
  await page.screenshot({ path: `test-results/code-${info.project.name}.png`, fullPage: true });
  await proposal.getByRole("button", { name: "Prepare apply review" }).click();
  await page.goto("/approvals");
  const applyResponse = page.waitForResponse(response => response.url().endsWith("/approve") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Approve & apply", exact: true }).last().click();
  expect((await applyResponse).ok()).toBe(true);
  await page.goto("/settings#advanced");
  await expect(proposal).toContainText("applied:");
  await proposal.getByRole("button", { name: "Prepare rollback review" }).click();
  await page.goto("/approvals");
  const rollbackResponse = page.waitForResponse(response => response.url().endsWith("/approve") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Approve & rollback", exact: true }).last().click();
  expect((await rollbackResponse).ok()).toBe(true);
  await page.goto("/settings#advanced");
  await expect(proposal).toContainText("restored:");
});

import { expect, test } from "@playwright/test";

test("approve a PC job, see live output, stop it and retain its history", async ({ page }, info) => {
  test.setTimeout(60_000);
  const marker = `pc-job-${info.project.name}-${Date.now()}`;
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill(`pc background 45 Desktop: Write-Output '${marker}'; Start-Sleep -Seconds 40`);
  await box.press("Enter");
  const card = page.getByRole("article").filter({ hasText: marker });
  await expect(card.getByTestId("approval-status")).toHaveText("Waiting for you", { timeout: 30_000 });
  await card.getByRole("button", { name: "Approve & run", exact: true }).click();
  await expect(card.getByTestId("approval-status")).toHaveText("Started");
  await page.goto("/settings#computer");
  const job = page.getByTestId("pc-job-row").filter({ hasText: marker });
  await expect(job.getByTestId("pc-job-state")).toHaveText("running");
  await job.getByRole("button", { name: /View output for/ }).click();
  await expect(job.getByTestId("pc-job-output")).toContainText(marker);
  await job.getByRole("button", { name: /Stop job/ }).click();
  await expect(job.getByTestId("pc-job-state")).toHaveText("stopped");
  await page.reload();
  await expect(job.getByTestId("pc-job-state")).toHaveText("stopped");
  await job.getByRole("button", { name: /View output for/ }).click();
  await expect(job.getByTestId("pc-job-output")).toContainText(marker);
  await expect(page.getByText("Checking output here uses no AI tokens.", { exact: false })).toBeVisible();
});

test("a completed PC job shows its actual output", async ({ page }, info) => {
  test.setTimeout(60_000);
  const marker = `pc-done-${info.project.name}-${Date.now()}`;
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill(`pc background 20 Desktop: Write-Output '${marker}'`);
  await box.press("Enter");
  const card = page.getByRole("article").filter({ hasText: marker });
  await expect(card.getByTestId("approval-status")).toHaveText("Waiting for you", { timeout: 30_000 });
  await card.getByRole("button", { name: "Approve & run", exact: true }).click();
  await expect(card.getByTestId("approval-status")).toHaveText("Started");
  await page.goto("/settings#computer");
  const job = page.getByTestId("pc-job-row").filter({ hasText: marker });
  await expect(job.getByTestId("pc-job-state")).toHaveText("completed");
  await job.getByRole("button", { name: /View output for/ }).click();
  await expect(job.getByTestId("pc-job-output")).toContainText(marker);
  await expect(job.getByRole("button", { name: /Stop job/ })).toHaveCount(0);
});

import { expect, test } from "@playwright/test";
import fs from "node:fs/promises";

test("a PDF slide request returns a real PDF in the originating chat", async ({ page }, info) => {
  test.setTimeout(90000);
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Message" });
  await input.fill(`Make 5 PDF slides about NLP ${info.project.name}-${Date.now()}`);
  await input.press("Enter");
  const link = page.getByRole("link", { name: /^Download .*\.pdf$/ }).last();
  await expect(link).toBeVisible({ timeout: 60000 });
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  const bytes = await fs.readFile((await download.path())!);
  expect(bytes.subarray(0, 5).toString()).toBe("%PDF-");
  await expect(page.getByText("5 PDF slides, with source links.")).toBeVisible();
  await page.screenshot({ path: `test-results/pdf-finished-${info.project.name}.png`, fullPage: true });
});

test("Google Slides keeps the local file and waits for Google approval", async ({ page, request }, info) => {
  test.setTimeout(90000);
  const original = await (await request.get("http://127.0.0.1:8100/api/google/status")).json();
  try {
  await page.goto("/settings#connections");
  const connect = page.getByRole("link", { name: /^(Connect Google|Connect again)$/ });
  await connect.click();
  await expect(page.getByText("Connected as you@example.com", { exact: true })).toBeVisible();
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Message" });
  await input.fill(`Make 5 Google Slides about NLP ${info.project.name}-${Date.now()}`);
  await input.press("Enter");
  await expect(page.getByRole("link", { name: /^Download .*\.pptx$/ }).last()).toBeVisible({ timeout: 40000 });
  await expect(page.getByText("5 editable slides", { exact: false })).toBeVisible();
  await expect(page.getByText(/Google creation is waiting for your approval/)).toBeVisible();
  const review = page.getByRole("region", { name: "Presentation review" });
  await expect(review).toBeVisible();
  await review.getByText("1. Introduction", { exact: true }).click();
  await expect(review.getByText("Speaker notes", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve & create", exact: true })).toBeVisible();
  await page.screenshot({ path: `test-results/google-slides-${info.project.name}.png`, fullPage: true });
  } finally {
    if (!original.connected) await request.delete("http://127.0.0.1:8100/api/google/connection");
  }
});

test("a slide topic produces a downloadable PowerPoint with background progress", async ({ page }, info) => {
  const topic = `Make 5 slides about NLP ${info.project.name}-${Date.now()}`;
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Message" });
  await input.fill(topic);
  await input.press("Enter");
  await expect(page.getByRole("status", { name: /Task \d+ progress/ })).toBeVisible({ timeout: 20000 });
  await expect(page.getByRole("progressbar", { name: "Task steps completed" })).toBeVisible();
  await page.screenshot({ path: `test-results/documents-progress-${info.project.name}.png`, fullPage: true });
  const link = page.getByRole("link", { name: /^Download .*\.pptx$/ }).last();
  await expect(link).toBeVisible({ timeout: 30000 });
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  expect(download.suggestedFilename()).toMatch(/\.pptx$/);
  const file = await download.path();
  const bytes = await fs.readFile(file!);
  expect(bytes.subarray(0, 2).toString()).toBe("PK");
  await expect(page.getByText("5 editable slides", { exact: false })).toBeVisible();
  await page.screenshot({ path: `test-results/documents-finished-${info.project.name}.png`, fullPage: true });
});

test("background task limits are editable in Settings", async ({ page, request }, info) => {
  await page.goto("/settings#tasks");
  const section = page.getByRole("region", { name: "Background tasks", exact: true });
  await expect(section).toBeVisible();
  await expect(section.getByRole("spinbutton", { name: "Task cost allowance in US dollars" })).toHaveValue("0.5");
  await expect(section.getByRole("spinbutton", { name: "Task time limit in seconds" })).toHaveValue("600");
  await expect(section.getByRole("combobox", { name: "Task retry limit" })).toHaveValue("1");
  await page.screenshot({ path: `test-results/documents-settings-${info.project.name}.png`, fullPage: true });
  try {
    await section.getByRole("spinbutton", { name: "Task cost allowance in US dollars" }).fill("0.45");
    await page.getByRole("button", { name: "Save changes", exact: true }).click();
    await expect(page.getByText("Saved. Applies from your next message or call.")).toBeVisible();
    await page.reload();
    await expect(section.getByRole("spinbutton", { name: "Task cost allowance in US dollars" })).toHaveValue("0.45");
  } finally {
    await request.patch("http://127.0.0.1:8100/api/settings", { data: { task_budget_usd: 0.5 } });
  }
});

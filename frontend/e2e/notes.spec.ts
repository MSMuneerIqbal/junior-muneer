import { expect, test } from "@playwright/test";

test("class notes are saved to a named folder and can be read, edited, downloaded and restored", async ({ page }, info) => {
  const folder = `NLP ${info.project.name} ${Date.now()}`;
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Message" });
  await input.fill(`Make class notes in folder ${folder}: NLP works with human language. Tokenization divides a sentence into tokens. Sentiment analysis identifies expressed opinions.`);
  await input.press("Enter");
  const open = page.getByRole("link", { name: "Open saved notes", exact: true }).last();
  await expect(open).toBeVisible({ timeout: 30000 });
  const href = await open.getAttribute("href");
  await page.goto(href!);
  const detail = page.getByRole("article", { name: "Saved note" });
  await expect(detail.getByRole("heading", { name: "Class notes", exact: true })).toBeVisible();
  await expect(detail).toContainText(folder);
  await expect(detail).toContainText("Tokenization");
  await page.screenshot({ path: `test-results/notes-${info.project.name}.png`, fullPage: true });

  await detail.getByRole("button", { name: "Edit notes" }).click();
  await page.getByRole("textbox", { name: "Note title", exact: true }).fill(`Lecture one ${folder}`);
  await page.getByLabel("Note class date", { exact: true }).fill("2026-10-23");
  await page.getByRole("button", { name: "Save notes", exact: true }).click();
  await expect(detail.getByRole("heading", { name: `Lecture one ${folder}`, exact: true })).toBeVisible();
  await page.reload();
  await expect(detail).toContainText("2026-10-23");
  const [download] = await Promise.all([page.waitForEvent("download"), detail.getByRole("link", { name: "Download Markdown" }).click()]);
  expect(download.suggestedFilename()).toContain("2026-10-23");
  await detail.getByRole("button", { name: "Archive notes" }).click();
  await expect(detail.getByRole("button", { name: "Restore notes" })).toBeVisible();
  await detail.getByRole("button", { name: "Restore notes" }).click();
  await expect(detail.getByRole("button", { name: "Archive notes" })).toBeVisible();

  await page.getByRole("link", { name: "Back to notes", exact: false }).click();
  await page.getByRole("textbox", { name: "Search notes" }).fill(folder);
  await expect(page.getByRole("link", { name: `Lecture one ${folder}`, exact: false })).toBeVisible();
  await page.getByLabel("New Notes folder name", { exact: true }).fill(`${folder} exams`);
  await page.getByRole("button", { name: "Create folder", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Notes folder filter" })).toContainText(`${folder} exams`);
  await page.screenshot({ path: `test-results/notes-folders-${info.project.name}.png`, fullPage: true });
});

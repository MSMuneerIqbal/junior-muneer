import { expect, test } from "@playwright/test";

test("clear commands start a fresh dashboard session with zero AI cost", async ({ page, request }) => {
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });
  const secret = `Old history ${Date.now()}`;
  await box.fill(secret); await box.press("Enter");
  await expect(page).toHaveURL(/\?c=\d+/);
  const oldId = new URL(page.url()).searchParams.get("c");
  await expect.poll(async () => (await (await request.get(`http://127.0.0.1:8100/api/conversations/${oldId}/messages`)).json()).length).toBe(2);
  await box.fill("/clear"); await box.press("Enter");
  await expect(page.getByText(/Fresh session started/).first()).toBeVisible();
  await expect(page.locator("main")).not.toContainText(secret);
  const newId = new URL(page.url()).searchParams.get("c");
  expect(newId).not.toBe(oldId);
  expect((await request.get(`http://127.0.0.1:8100/api/conversations/${oldId}/messages`)).status()).toBe(404);
  const summary = await request.get(`http://127.0.0.1:8100/api/conversations/${newId}/summary`);
  expect((await summary.json()).cost_usd).toBe(0);
  await box.fill("cls"); await box.press("Enter");
  await expect.poll(() => new URL(page.url()).searchParams.get("c")).not.toBe(newId);
});

test("Notes gallery shows original files in folders and public sharing is reviewable", async ({ page, request }, info) => {
  test.setTimeout(90000);
  const folder = `Class ${info.project.name} ${Date.now()}`;
  const prefix = `Lecture-${info.project.name}`;
  await page.goto("/notes");
  await page.getByLabel("New Notes folder name", { exact: true }).fill(folder);
  await page.getByRole("button", { name: "Create folder", exact: true }).click();
  await expect(page.getByRole("button", { name: "All folders", exact: true })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Notes folder filter" })).toHaveValue(/\d+/);
  const plain = "Tokenization divides text into tokens. Save this original exactly.";
  await page.getByLabel("Upload library files", { exact: true }).setInputFiles([
    { name: `${prefix}.txt`, mimeType: "text/plain", buffer: Buffer.from(plain) },
    { name: `${prefix}.md`, mimeType: "text/markdown", buffer: Buffer.from("# Lecture\n\nClass material.") },
    { name: `${prefix}.pdf`, mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 synthetic gallery example") },
    { name: `${prefix}.docx`, mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: Buffer.from("PK synthetic gallery example") },
    { name: `${prefix}.png`, mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aVxkAAAAASUVORK5CYII=", "base64") },
  ]);
  for (const ext of ["txt", "md", "pdf", "docx", "png"]) await expect(page.getByRole("link", { name: `Open file ${prefix}.${ext}`, exact: true })).toBeVisible();
  await page.getByRole("button", { name: "All folders", exact: true }).click();
  await expect(page.getByRole("button", { name: `Open folder ${folder}`, exact: true })).toBeVisible();
  await page.screenshot({ path: `test-results/folders-${info.project.name}.png`, fullPage: true });
  await page.getByRole("button", { name: `Open folder ${folder}`, exact: true }).click();
  await page.screenshot({ path: `test-results/gallery-${info.project.name}.png`, fullPage: true });
  await page.getByRole("link", { name: `Open file ${prefix}.txt`, exact: true }).click();
  const detail = page.getByRole("article", { name: "Saved file", exact: true });
  await expect(detail.getByLabel("File text preview")).toContainText(plain);
  const [download] = await Promise.all([page.waitForEvent("download"), detail.getByRole("link", { name: "Download original" }).click()]);
  expect(download.suggestedFilename()).toBe(`${prefix}.txt`);
  await request.get("http://127.0.0.1:8100/api/google/connect");
  await detail.getByRole("combobox", { name: "File Drive access" }).selectOption("reader");
  await detail.getByRole("button", { name: "Save to Drive", exact: true }).click();
  const card = page.getByRole("article", { name: `Google Drive file_transfer: Drive: ${prefix}.txt`, exact: true });
  await expect(card.getByTestId("approval-status")).toHaveText("Waiting for you");
  await expect(card).toContainText("Anyone with the link can view");
  await card.getByRole("button", { name: "Approve & save", exact: true }).click();
  await expect(card.getByTestId("approval-status")).toHaveText("Sent");
  await expect(detail.getByRole("link", { name: "Open in Drive", exact: true })).toBeVisible();
  await detail.getByRole("combobox", { name: "File Drive access" }).selectOption("writer");
  await detail.getByRole("button", { name: "Update Drive sharing", exact: true }).click();
  await expect(card.getByTestId("approval-status")).toHaveText("Waiting for you");
  await expect(card).toContainText("Anyone with the link can edit");
  await card.getByRole("button", { name: "Approve & save", exact: true }).click();
  await expect(card.getByTestId("approval-status")).toHaveText("Sent");
});

import { expect, test } from "@playwright/test";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import path from "node:path";

test("actual document copy and ZIP WhatsApp delivery use reviewable approval cards", async ({ page, request }, info) => {
  test.setTimeout(90000);
  const root = mkdtempSync(path.resolve(`test-results/junior-transfer-${info.project.name}-`));
  const target = path.join(root, "NLP");
  const name = `Lecture-${info.project.name}.pdf`;
  const bytes = Buffer.from("%PDF-1.4 actual uploaded document bytes\n");
  try {
    const uploaded = await request.post("http://127.0.0.1:8100/api/files", { multipart: { file: { name, mimeType: "application/pdf", buffer: bytes } } });
    const file = await uploaded.json();
    await page.goto("/");
    const box = page.getByRole("textbox", { name: "Message" });
    await box.fill(`place document ${JSON.stringify({ destination: target, file_number: file.id })}\n${file.tag}`);
    await box.press("Enter");
    const copy = page.getByRole("article", { name: `Your PC file_transfer: Place ${name}`, exact: true });
    await expect(copy.getByTestId("approval-status")).toHaveText("Waiting for you");
    await expect(copy.getByRole("link", { name: "Download prepared file" })).toBeVisible();
    await expect(copy.getByRole("button", { name: "Edit", exact: true })).toBeDisabled();
    await copy.getByRole("button", { name: "Approve & copy", exact: true }).click();
    await expect(copy.getByTestId("approval-status")).toHaveText("Done");
    expect(readFileSync(path.join(target, name))).toEqual(bytes);
    mkdirSync(path.join(target, "Empty"));
    writeFileSync(path.join(target, "Extra.txt"), "Tokenization class");

    // Connect only the fake Google account. No live credentials are used by this server.
    await request.get("http://127.0.0.1:8100/api/google/connect");
    const status = await request.get("http://127.0.0.1:8100/api/google/status");
    expect((await status.json()).connected).toBe(true);
    await box.fill(`zip folder ${JSON.stringify({ folder: target, send_whatsapp: true })}`);
    await box.press("Enter");
    const zip = page.getByRole("article", { name: "Your WhatsApp file_transfer: Send ZIP NLP.zip", exact: true });
    await expect(zip.getByTestId("approval-status")).toHaveText("Waiting for you");
    await expect(zip).toContainText("private");
    await zip.screenshot({ path: `test-results/transfer-${info.project.name}.png` });
    await zip.getByRole("button", { name: "Approve & send", exact: true }).click();
    await expect(zip.getByTestId("approval-status")).toHaveText("Sent");
    await expect(zip.getByRole("link", { name: "Open file" })).toHaveAttribute("href", /drive.google.com/);
    await page.goto("/settings#connections");
    await expect(page.getByRole("link", { name: "Allow existing Drive folders" })).toHaveAttribute("href", /drive_folders=true/);
  } finally {
    // Only this test's verified, newly-created temporary directory is removed.
    expect(root.startsWith(path.resolve("test-results/junior-transfer-"))).toBe(true);
    rmSync(root, { recursive: true, force: true });
  }
});

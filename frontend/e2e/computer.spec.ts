import path from "node:path";

import { expect, test } from "@playwright/test";

test("Settings → Computer: on/off, allowed folders, add and remove, the blocked list", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "one shared database: once is enough");
  await page.goto("/settings#computer");
  await expect(page.getByRole("heading", { name: "Computer" })).toBeVisible();
  await expect(page.getByRole("switch", { name: "Computer tools" })).toHaveAttribute("aria-checked", "true");
  const allDrives = page.getByRole("switch", { name: "Allow all local drives" });
  await expect(allDrives).toHaveAttribute("aria-checked", "false");
  await allDrives.click();
  await expect(allDrives).toHaveAttribute("aria-checked", "true");
  await page.reload();
  await expect(allDrives).toHaveAttribute("aria-checked", "true");
  await allDrives.click();
  await expect(allDrives).toHaveAttribute("aria-checked", "false");
  const folders = page.getByRole("list", { name: "Allowed folders" });
  await expect(folders.getByRole("listitem")).toHaveCount(3); // Desktop, Documents, Downloads
  await expect(page.getByText(/\.env, keys and certificates/)).toBeVisible();

  const extra = path.resolve("e2e");
  await page.getByRole("textbox", { name: "Folder to allow" }).fill(extra);
  await page.getByRole("button", { name: "Add folder" }).click();
  await expect(folders.getByText(extra)).toBeVisible();
  await page.getByRole("button", { name: `Remove ${extra}` }).click();
  await expect(folders.getByText(extra)).toHaveCount(0);

  // A blocked folder is refused with the reason.
  await page.getByRole("textbox", { name: "Folder to allow" }).fill("C:\\Windows");
  await page.getByRole("button", { name: "Add folder" }).click();
  await expect(page.locator("#computer").getByRole("alert")).toContainText("system folder");
});

test("Junior hands a PC job to the Computer Agent; the file card waits for you and can be rejected", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "one shared database: once is enough");
  const name = `junior-e2e-${Date.now()}.txt`;
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill(`pc write Desktop/${name}: hello from the e2e test`);
  await box.press("Enter");
  const card = page.getByRole("article", { name: new RegExp(`Your PC file: Create .*${name.replace(".", "\\.")}`) });
  await expect(card.getByTestId("approval-status")).toHaveText("Waiting for you", { timeout: 30_000 });
  await expect(card.getByText("hello from the e2e test")).toBeVisible();
  await card.getByRole("button", { name: "Reject" }).click();
  await expect(card.getByTestId("approval-status")).toHaveText("Rejected");
});

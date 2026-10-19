import { expect, test } from "@playwright/test";

test("the Inbox page lists sorted emails and checks Gmail on demand", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "one shared database: once is enough");
  // The pretend Google is connected by the Connect Google test (google.spec.ts runs first).
  await page.goto("/inbox");
  await expect(page.getByRole("heading", { name: "Inbox" })).toBeVisible();
  await page.getByRole("button", { name: "↻ Check now" }).click(); // the first check only starts the clock
  await expect(page.getByRole("status")).toHaveText(/Nothing new\.|new email/);
  await page.getByRole("tab", { name: "All" }).click();
  await expect(page.getByRole("tab", { name: "All" })).toHaveAttribute("aria-selected", "true");
});

test("Settings has the Gmail switches", async ({ page }) => {
  await page.goto("/settings#news");
  await expect(page.getByRole("switch", { name: "Watch my Gmail inbox" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("switch", { name: "Send important emails to my WhatsApp" })).toHaveAttribute("aria-checked", "true");
});

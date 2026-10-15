import { expect, test } from "@playwright/test";

test("the Mode menu under the message box works like Claude's", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Mode: Auto" }).click();
  const menu = page.getByRole("menu", { name: "Mode" });
  await expect(menu.getByText("Always asks before doing anything")).toBeVisible();

  await menu.getByRole("menuitemradio", { name: /Manual/ }).click();
  await expect(page.getByRole("button", { name: "Mode: Manual" })).toBeVisible();

  // Number keys pick a mode while the menu is open.
  await page.getByRole("button", { name: "Mode: Manual" }).click();
  await page.keyboard.press("3");
  await expect(page.getByRole("button", { name: "Mode: Plan" })).toBeVisible();

  await page.getByRole("button", { name: "Mode: Plan" }).click();
  await page.getByRole("menuitemcheckbox", { name: "Pause everything" }).click();
  await expect(page.getByRole("button", { name: "Mode: Plan, paused" })).toBeVisible();
  await expect(page.getByText("Everything is paused", { exact: false })).toBeVisible();

  // Back to normal, so other tests start from the default.
  await page.getByRole("button", { name: "Mode: Plan, paused" }).click();
  await page.getByRole("menuitemcheckbox", { name: "Pause everything" }).click();
  await page.getByRole("button", { name: "Mode: Plan" }).click();
  await page.keyboard.press("1");
  await expect(page.getByRole("button", { name: "Mode: Auto" })).toBeVisible();
  await expect(page.getByText("Everything is paused", { exact: false })).toHaveCount(0);
});

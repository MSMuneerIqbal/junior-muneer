import { expect, test } from "@playwright/test";

test("Settings is its own page: a left menu, one section at a time", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "the side menu is for big screens; phones get a picker");
  await page.goto("/");
  await page.getByRole("link", { name: "Settings" }).click(); // the same tab
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole("link", { name: "← Back to Junior" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Profile" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Permissions" })).toBeHidden();
  await expect(page.getByText("Search chats")).toHaveCount(0); // no chat list here

  const menu = page.getByRole("navigation", { name: "Settings sections" });
  await menu.getByRole("button", { name: "Permissions" }).click();
  await expect(page.getByRole("region", { name: "Permissions" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Profile" })).toBeHidden();
  await expect(menu.getByRole("button", { name: "Permissions" })).toHaveAttribute("aria-current", "page");
  await expect(page).toHaveURL(/\/settings#permissions$/);
});

test("on a phone the sections are a picker", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "phone", "phones only");
  await page.goto("/settings");
  await page.getByRole("combobox", { name: "Settings section" }).selectOption("news");
  await expect(page.getByRole("region", { name: "News & email" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Profile" })).toBeHidden();
});

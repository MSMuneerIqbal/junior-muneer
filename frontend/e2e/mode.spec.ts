import { expect, test } from "@playwright/test";

test("the Permissions menu under the message box explains and switches modes", async ({ page }) => {
  await page.goto("/");
  const button = page.getByRole("button", { name: "Permissions: Use my rules" });
  await button.click();
  const menu = page.getByRole("menu", { name: "Permissions" });
  await expect(menu.getByText("Every action waits for your OK", { exact: false })).toBeVisible();

  await menu.getByRole("menuitemradio", { name: /Ask everything/ }).click();
  await expect(page.getByRole("button", { name: "Permissions: Ask everything" })).toBeVisible();

  await page.getByRole("button", { name: "Permissions: Ask everything" }).click();
  await page.getByRole("menu").getByRole("menuitemradio", { name: /Pause everything/ }).click();
  await expect(page.getByRole("button", { name: "Permissions: Pause everything" })).toBeVisible();
  await expect(page.getByText("Everything is paused", { exact: false })).toBeVisible();

  // Back to normal, so other tests start from the default.
  await page.getByRole("button", { name: "Permissions: Pause everything" }).click();
  await page.getByRole("menu").getByRole("menuitemradio", { name: /Use my rules/ }).click();
  await expect(page.getByRole("button", { name: "Permissions: Use my rules" })).toBeVisible();
  await expect(page.getByText("Everything is paused", { exact: false })).toHaveCount(0);
});

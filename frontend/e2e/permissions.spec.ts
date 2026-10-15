import { expect, test } from "@playwright/test";

test("permission rules can be changed, locked ones can't", async ({ page }) => {
  await page.goto("/settings#permissions");
  const linkedin = page.getByRole("radiogroup", { name: "Post on LinkedIn" });
  await expect(linkedin.getByRole("radio", { name: "Ask" })).toHaveAttribute("aria-checked", "true");

  await linkedin.getByRole("radio", { name: "Auto" }).click();
  await expect(linkedin.getByRole("radio", { name: "Auto" })).toHaveAttribute("aria-checked", "true");
  await page.reload();
  await expect(
    page.getByRole("radiogroup", { name: "Post on LinkedIn" }).getByRole("radio", { name: "Auto" }),
  ).toHaveAttribute("aria-checked", "true");

  // Locked types show a lock, not buttons.
  await expect(page.getByRole("radiogroup", { name: "Merge a pull request" })).toHaveCount(0);
  await expect(page.getByText("Merge a pull request")).toBeVisible();

  // Put it back so other runs start from the default.
  await page.getByRole("radiogroup", { name: "Post on LinkedIn" }).getByRole("radio", { name: "Ask" }).click();
  await expect(
    page.getByRole("radiogroup", { name: "Post on LinkedIn" }).getByRole("radio", { name: "Ask" }),
  ).toHaveAttribute("aria-checked", "true");
});

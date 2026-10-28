import { expect, test } from "@playwright/test";

test("permission rules can be changed, while payments remain locked", async ({ page }) => {
  await page.goto("/settings#permissions");
  const linkedin = page.getByRole("radiogroup", { name: "Post on LinkedIn" });
  await expect(linkedin.getByRole("radio", { name: "Ask" })).toHaveAttribute("aria-checked", "true");

  await linkedin.getByRole("radio", { name: "Auto" }).click();
  await expect(linkedin.getByRole("radio", { name: "Auto" })).toHaveAttribute("aria-checked", "true");
  await page.reload();
  await expect(
    page.getByRole("radiogroup", { name: "Post on LinkedIn" }).getByRole("radio", { name: "Auto" }),
  ).toHaveAttribute("aria-checked", "true");

  const terminal = page.getByRole("radiogroup", { name: "Run a terminal command on your PC" });
  await terminal.getByRole("radio", { name: "Auto" }).click();
  await expect(terminal.getByRole("radio", { name: "Auto" })).toHaveAttribute("aria-checked", "true");
  await page.reload();
  await expect(terminal.getByRole("radio", { name: "Auto" })).toHaveAttribute("aria-checked", "true");
  await terminal.getByRole("radio", { name: "Ask" }).click();
  await expect(terminal.getByRole("radio", { name: "Ask" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("radiogroup", { name: "Make a payment" })).toHaveCount(0);
  await expect(page.getByText("Make a payment", { exact: true })).toBeVisible();

  // Put it back so other runs start from the default.
  await page.getByRole("radiogroup", { name: "Post on LinkedIn" }).getByRole("radio", { name: "Ask" }).click();
  await expect(
    page.getByRole("radiogroup", { name: "Post on LinkedIn" }).getByRole("radio", { name: "Ask" }),
  ).toHaveAttribute("aria-checked", "true");
});

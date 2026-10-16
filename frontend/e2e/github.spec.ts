import { expect, test } from "@playwright/test";

test("connect GitHub in the app: a code to approve on GitHub, then connected; disconnect works", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "one account for the whole test backend");
  await page.goto("/settings#connections");
  const row = page.getByText("GitHub (read-only for now)").locator("xpath=ancestor::*[.//button][1]");
  await row.getByRole("button", { name: "Connect GitHub" }).click();

  const flow = page.getByRole("group", { name: "Connect GitHub" });
  await expect(flow.getByTestId("github-code")).toHaveText("FAKE-1234");
  await expect(flow.getByRole("link", { name: "Open GitHub ↗" })).toHaveAttribute("href", "https://github.com/login/device");
  await expect(flow.getByRole("status")).toHaveText("Waiting for you to approve on GitHub…");

  // The pretend GitHub approves on the second check.
  await expect(page.getByText("Connected as @fake-github-user")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Connect GitHub" })).toHaveCount(0);

  await page.getByRole("button", { name: "Disconnect" }).click();
  await expect(page.getByRole("button", { name: "Connect GitHub" })).toBeVisible();
});

import { expect, test } from "@playwright/test";

test("Updates show reviewed revisions, preserve dirty work and surface failures", async ({ page }, info) => {
  let dirty = true;
  let proposed = 0;
  await page.route("**/api/updates", route => route.fulfill({ json: {
    supervised: true, progress: { state: "rolled_back", step: "Previous release restored; review before resuming." },
    review: { id: "fixture", base: "a".repeat(40), target: "b".repeat(40), changes: "frontend/page.tsx | 2 ++", dirty, supervised: true },
  } }));
  await page.route("**/api/updates/check", async route => {
    dirty = false;
    await route.fulfill({ json: { id: "fixture" } });
  });
  await page.route("**/api/updates/propose", async route => {
    proposed++;
    await route.fulfill({ status: 409, json: { detail: "Source changed. Check again before applying." } });
  });
  await page.goto("/settings#advanced");
  const group = page.getByRole("group", { name: "Junior updates" });
  await expect(group).toBeVisible();
  await expect(group).toContainText("Previous release restored");
  await expect(group.getByRole("button", { name: "Prepare update review" })).toBeDisabled();
  await group.getByRole("button", { name: "Check for updates" }).click();
  await expect(group.getByRole("button", { name: "Prepare update review" })).toBeEnabled();
  await group.getByRole("button", { name: "Prepare update review" }).click();
  await expect(group).toContainText("Source changed. Check again");
  expect(proposed).toBe(1);
  await page.screenshot({ path: `test-results/updates-${info.project.name}.png`, fullPage: true });
});

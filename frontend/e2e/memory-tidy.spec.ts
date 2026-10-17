import { expect, test } from "@playwright/test";

test("tidy up memories: a duplicate is archived with its reason, and can be restored", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "one tidy-up at a time on the shared test database");
  const tag = `${info.project.name}-${Date.now().toString(36)}`;
  const fact = `My rate is $25/hr ${tag}`;
  await page.goto("/memory");
  for (let n = 0; n < 2; n++) {
    await page.getByRole("textbox", { name: "New memory" }).fill(fact);
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByRole("listitem").filter({ hasText: fact })).toHaveCount(n + 1);
  }

  await page.getByRole("button", { name: "🧹 Tidy up now" }).click();
  const tidied = page.getByRole("region", { name: "Tidied up" });
  await expect(tidied.getByRole("listitem").filter({ hasText: fact })).toContainText(/Same as \d+\./, { timeout: 15_000 });
  const mine = page.getByRole("list", { name: "Your memories" });
  await expect(mine.getByRole("listitem").filter({ hasText: fact })).toHaveCount(1); // one kept

  await tidied.getByRole("button", { name: `Restore: ${fact}` }).click();
  await expect(tidied.getByRole("listitem").filter({ hasText: fact })).toHaveCount(0);
  await expect(mine.getByRole("listitem").filter({ hasText: fact })).toHaveCount(2);
});

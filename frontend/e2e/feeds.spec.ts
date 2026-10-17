import { expect, test } from "@playwright/test";

test("follow a feed on the News page: its posts show, and you can stop following it", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "one feed list on the shared test database");
  const url = "https://openai.com/news/rss.xml"; // a sample feed in the fake-AI test backend
  await page.goto("/news");
  await page.getByRole("tab", { name: "Your feeds" }).click();

  const following = page.getByRole("region", { name: "Feeds you follow" });
  if (await following.getByRole("listitem").count()) {
    // Left over from an earlier run on this test backend.
    await following.getByRole("button", { name: /Stop following/ }).first().click();
  }
  await page.getByRole("textbox", { name: "Feed address" }).fill(url);
  await page.getByRole("button", { name: "Follow", exact: true }).click();
  await expect(following.getByRole("listitem")).toHaveCount(1, { timeout: 15_000 });
  await expect(following).toContainText("2 posts");

  const posts = page.getByRole("region", { name: "Newest posts" });
  await expect(posts.getByRole("link", { name: /Introducing GPT-7 \(sample\)/ })).toHaveAttribute("href", "https://openai.com/index/sample-gpt-7/");

  // Following it twice is refused in plain words.
  await page.getByRole("textbox", { name: "Feed address" }).fill(url);
  await page.getByRole("button", { name: "Follow", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "already follow" })).toHaveText("You already follow that feed.");

  await following.getByRole("button", { name: /Stop following/ }).click();
  await expect(following.getByRole("listitem")).toHaveCount(0);
});

import { expect, test } from "@playwright/test";

test("AI and Pakistan news questions go to the news agents, with their steps in Show work", async ({ page }) => {
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });

  await box.fill("What's the latest AI news?");
  await box.press("Enter");
  // The first question builds today's digest first.
  await expect(page.getByText(/From today's digest: Introducing GPT-7 \(sample/)).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "▸ Show work" }).click();
  await expect(page.getByText("Asking the AI-News-Agent")).toBeVisible();
  await expect(page.getByText(/official sources/).first()).toBeVisible();

  await box.fill("What's trending in Pakistan news?");
  await box.press("Enter");
  await expect(page.getByText(/From today's digest: babar azam/)).toBeVisible();
});

test("the News page builds and shows sourced digests for AI and Pakistan", async ({ page }) => {
  await page.goto("/news");
  await page.getByRole("tab", { name: "AI" }).click();
  const build = page.getByRole("button", { name: /Build it now|Refresh/ });
  await build.click();
  // The day's top 5 first; the rest under "More news".
  const top = page.getByRole("region", { name: "Top 5" });
  await expect(top.getByText("#1", { exact: true })).toBeVisible({ timeout: 20_000 });
  expect(await top.getByRole("listitem").count()).toBeLessThanOrEqual(5);
  await expect(page.getByRole("region", { name: "New models and releases" })).toBeHidden();
  await page.getByText(/More news: all \d+ stories/).click();
  const models = page.getByRole("region", { name: "New models and releases" });
  await expect(models.getByText("Introducing GPT-7 (sample)")).toBeVisible({ timeout: 20_000 });
  await expect(models.getByRole("link", { name: /OpenAI ·/ }).first()).toHaveAttribute("href", "https://openai.com/index/sample-gpt-7/");
  await expect(page.getByTestId("digest-info")).toContainText("articles from 17 sources");
  await expect(page.getByText("Live rankings are off")).toBeVisible();

  await page.getByRole("tab", { name: "Pakistan" }).click();
  await page.getByRole("button", { name: /Build it now|Refresh/ }).click();
  await expect(page.getByRole("region", { name: "Top 5" })).toBeVisible({ timeout: 20_000 });
  await page.getByText(/More news: all \d+ stories/).click();
  const trending = page.getByRole("region", { name: "Trending online" });
  await expect(trending.getByText("babar azam")).toBeVisible({ timeout: 20_000 });
  await expect(trending.getByRole("link", { name: /Google Trends Pakistan ·/ })).toHaveAttribute("href", /trends\.google\.com\/trending\?geo=PK#babar/);
});

test("the top 5 AI news can be emailed now from Settings", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "one shared database: once is enough");
  await page.goto("/news");
  await page.getByRole("tab", { name: "AI" }).click();
  await expect(page.getByRole("region", { name: "Top 5" })).toBeVisible({ timeout: 20_000 }); // built by the test above
  await page.goto("/settings#news");
  await expect(page.getByRole("switch", { name: "Email me the top 5 AI news every morning" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByText("me@example.com")).toBeVisible();
  await page.getByRole("button", { name: "Send it now" }).click();
  await expect(page.getByRole("status").filter({ hasText: /Sent the top \d AI news to me@example\.com\./ })).toBeVisible();
  await expect(page.getByText(/last sent \d{4}-\d\d-\d\d/)).toBeVisible();
});

test("the morning digest can be switched off and its time changed", async ({ page, request }) => {
  const before = await (await request.get("http://127.0.0.1:8100/api/settings")).json();
  await request.patch("http://127.0.0.1:8100/api/settings", { data: { news_digest_enabled: true } });
  try {
  await page.goto("/settings#news");
  const toggle = page.getByRole("switch", { name: "Build the news digests every morning" });
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await page.getByLabel("Morning digest time").fill("06:45");
  await toggle.click();
  const [saved] = await Promise.all([
    page.waitForResponse((response) => response.url().endsWith("/api/settings") && response.request().method() === "PATCH"),
    page.getByRole("button", { name: "Save" }).click(),
  ]);
  expect((await saved.json()).news_digest_enabled).toBe(false);
  await page.reload();
  await expect(page.getByRole("switch", { name: "Build the news digests every morning" })).toHaveAttribute("aria-checked", "false");
  await expect(page.getByLabel("Morning digest time")).toHaveValue("06:45");
  } finally {
    // Restore even if a UI assertion fails; desktop and phone share this throwaway database.
    await request.patch("http://127.0.0.1:8100/api/settings", { data: {
      news_digest_enabled: before.news_digest_enabled, news_digest_time: before.news_digest_time,
    } });
  }
});

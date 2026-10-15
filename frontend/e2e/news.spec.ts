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
  const models = page.getByRole("region", { name: "New models and releases" });
  await expect(models.getByText("Introducing GPT-7 (sample)")).toBeVisible({ timeout: 20_000 });
  await expect(models.getByRole("link", { name: /OpenAI ·/ }).first()).toHaveAttribute("href", "https://openai.com/index/sample-gpt-7/");
  await expect(page.getByTestId("digest-info")).toContainText("articles from 16 sources");
  await expect(page.getByText("Live rankings are off")).toBeVisible();

  await page.getByRole("tab", { name: "Pakistan" }).click();
  await page.getByRole("button", { name: /Build it now|Refresh/ }).click();
  const trending = page.getByRole("region", { name: "Trending online" });
  await expect(trending.getByText("babar azam")).toBeVisible({ timeout: 20_000 });
  await expect(trending.getByRole("link", { name: /Google Trends Pakistan ·/ })).toHaveAttribute("href", /trends\.google\.com\/trending\?geo=PK#babar/);
});

test("the morning digest can be switched off and its time changed", async ({ page }) => {
  await page.goto("/settings#news");
  const toggle = page.getByRole("switch", { name: "Build the news digests every morning" });
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await page.getByLabel("Morning digest time").fill("06:45");
  await toggle.click();
  await page.getByRole("button", { name: "Save" }).click();
  await page.reload();
  await expect(page.getByRole("switch", { name: "Build the news digests every morning" })).toHaveAttribute("aria-checked", "false");
  await expect(page.getByLabel("Morning digest time")).toHaveValue("06:45");
  // Back to the default for other runs.
  await page.getByRole("switch", { name: "Build the news digests every morning" }).click();
  await page.getByLabel("Morning digest time").fill("07:30");
  await page.getByRole("button", { name: "Save" }).click();
});

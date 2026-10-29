import { expect, test } from "@playwright/test";

test("scheduled jobs can be turned off and on and share news settings", async ({ page, request }) => {
  try {
    await page.goto("/settings#scheduled");
    await expect(page.getByRole("heading", { name: "Scheduled jobs" })).toBeVisible();
    const news = page.getByRole("switch", { name: "Morning news digests" });
    await expect(news).toHaveAttribute("aria-checked", "true");
    await news.click();
    await expect(news).toHaveAttribute("aria-checked", "false");
    expect((await (await request.get("http://127.0.0.1:8100/api/settings")).json()).news_digest_enabled).toBe(false);
    await page.reload();
    await expect(news).toHaveAttribute("aria-checked", "false");
    await news.click();
    await expect(news).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("switch", { name: "Daily backup" })).toBeVisible();
  } finally {
    await request.patch("http://127.0.0.1:8100/api/scheduled-jobs/news", { data: { enabled: true } });
  }
});

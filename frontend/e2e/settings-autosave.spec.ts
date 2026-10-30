import { expect, test } from "@playwright/test";

test("model and other settings save automatically and survive reload", async ({ page, request }) => {
  const endpoint = "http://127.0.0.1:8100/api/settings";
  const original = await (await request.get(endpoint)).json();
  try {
    await page.goto("/settings#models");
    await request.patch(endpoint, { data: { news_digest_enabled: !original.news_digest_enabled } });
    const models = page.getByRole("radiogroup", { name: "Chat model" });
    await models.getByRole("radio", { name: /DeepSeek V4.1 Flash/ }).click();
    await expect.poll(async () => (await (await request.get(endpoint)).json()).main_model).toBe("deepseek:deepseek-flash");
    expect((await (await request.get(endpoint)).json()).news_digest_enabled).toBe(!original.news_digest_enabled);
    await expect.poll(async () => (await (await request.get("http://127.0.0.1:8100/api/models")).json()).agents.find((a: {agent: string}) => a.agent === "junior_muneer").model).toBe("deepseek:deepseek-flash");
    await page.reload();
    await expect(models.getByRole("radio", { name: /DeepSeek V4.1 Flash/ })).toHaveAttribute("aria-checked", "true");
    await page.goto("/settings#whatsapp");
    const mode = page.getByRole("combobox", { name: "WhatsApp action mode" });
    await mode.selectOption("rules");
    await expect.poll(async () => (await (await request.get(endpoint)).json()).whatsapp_action_mode).toBe("rules");
  } finally {
    await request.patch(endpoint, { data: { main_model: original.main_model, whatsapp_action_mode: original.whatsapp_action_mode, news_digest_enabled: original.news_digest_enabled } });
  }
});

test("settings save errors stay visible and do not falsely claim success", async ({ page }) => {
  await page.goto("/settings#models");
  await page.route("**/api/settings", async (route) => {
    if (route.request().method() === "PATCH") await route.fulfill({ status: 503, json: { detail: "Save unavailable" } });
    else await route.continue();
  });
  const models = page.getByRole("radiogroup", { name: "Chat model" });
  const desired = models.getByRole("radio", { name: /DeepSeek V4.1 Flash/ });
  const other = models.getByRole("radio", { name: /GPT-6 Luna/ });
  if (await desired.getAttribute("aria-checked") === "true") await other.click();
  else await desired.click();
  await expect(page.getByRole("status").filter({ hasText: "Save unavailable" })).toBeVisible();
});

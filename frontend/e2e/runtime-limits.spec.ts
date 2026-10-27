import { expect, test } from "@playwright/test";

test("Chat budget, shared AI-call quota and output limit persist with local runtime guidance", async ({ page, request }, info) => {
  await page.goto("/settings#budget");
  const section = page.getByRole("region", { name: "Budget", exact: true });
  await expect(section.getByRole("group", { name: "Runtime limits" })).toContainText("/clear starts fresh context");
  await expect(section.getByRole("spinbutton", { name: "Chat cost allowance in US dollars" })).toHaveValue("0.5");
  try {
    await section.getByRole("spinbutton", { name: "Chat cost allowance in US dollars" }).fill("0.35");
    await section.getByRole("spinbutton", { name: "AI calls per chat reply" }).fill("8");
    await section.getByRole("spinbutton", { name: "Output tokens per AI response" }).fill("4096");
    await page.getByRole("button", { name: "Save changes", exact: true }).click();
    await expect(page.getByText("Saved. Applies from your next message or call.")).toBeVisible();
    await page.reload();
    await expect(section.getByRole("spinbutton", { name: "Chat cost allowance in US dollars" })).toHaveValue("0.35");
    await expect(section.getByRole("spinbutton", { name: "AI calls per chat reply" })).toHaveValue("8");
    await expect(section.getByRole("spinbutton", { name: "Output tokens per AI response" })).toHaveValue("4096");
    await page.screenshot({ path: `test-results/runtime-limits-${info.project.name}.png`, fullPage: true });
  } finally {
    await request.patch("http://127.0.0.1:8100/api/settings", { data: { chat_budget_usd: .5, chat_max_model_calls: 16, max_output_tokens: 10000 } });
  }
});

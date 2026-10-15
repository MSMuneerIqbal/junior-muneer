import { expect, test } from "@playwright/test";

test("ideas to draft to planned, all from the Social page", async ({ page, request }, info) => {
  await request.put("http://127.0.0.1:8100/api/profile", {
    data: { headline: "AI engineer", proof: ["Built an MCP server for a hospital"] },
  });
  const tag = `${info.project.name}-${Date.now()}`;
  // Get ideas in the chat (the fake manager saves 3).
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill(`ideas ${tag}`);
  await box.press("Enter");
  await page.getByRole("button", { name: "▸ Show work" }).waitFor();

  await page.goto("/social");
  const ideas = page.getByRole("region", { name: "Ideas" });
  const idea = ideas.getByRole("listitem").filter({ hasText: `Fake idea 1: ${tag}` });
  await expect(idea).toBeVisible();

  // Dismiss one.
  await ideas.getByRole("listitem").filter({ hasText: `Fake idea 3: ${tag}` }).getByRole("button", { name: "Dismiss" }).click();
  await expect(ideas.getByText(`Fake idea 3: ${tag}`)).toHaveCount(0);

  // "Write it" opens the chat with the request ready; you press Send.
  await idea.getByRole("link", { name: "Write it" }).click();
  await expect(page.getByRole("textbox", { name: "Message" })).toHaveValue(/^Write idea \d+$/);
  await page.getByRole("textbox", { name: "Message" }).press("Enter");
  const card = page.getByRole("article").filter({ hasText: "(fake Humanizer)" }).last();
  await expect(card).toContainText("9/10", { timeout: 20_000 }); // the whole writing team runs first

  // Plan it for tomorrow 09:00.
  await card.getByRole("button", { name: "📅 Plan" }).click();
  const tomorrow = new Date(Date.now() + 24 * 3600 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  await card.getByLabel("Planned time").fill(`${tomorrow.getFullYear()}-${pad(tomorrow.getMonth() + 1)}-${pad(tomorrow.getDate())}T09:00`);
  await card.getByRole("button", { name: "Save" }).click();
  await expect(card.getByTestId("planned")).toContainText("📅");

  // The Social page shows it under Planned, and the idea is used (gone from Ideas).
  await page.goto("/social");
  await expect(page.getByRole("region", { name: "Planned" }).getByRole("article").filter({ hasText: "(fake Humanizer)" }).first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Ideas" }).getByText(`Fake idea 1: ${tag}`)).toHaveCount(0);
});

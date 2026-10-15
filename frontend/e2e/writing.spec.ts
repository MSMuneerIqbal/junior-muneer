import { expect, test } from "@playwright/test";

test("the writing team's steps show live and in Show work, and the card has the score", async ({ page, request }, info) => {
  await request.put("http://127.0.0.1:8100/api/profile", {
    data: { headline: "AI engineer", proof: ["Built an MCP server for a hospital"] },
  });
  const tag = `${info.project.name}-${Date.now()}`;
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill(`write launch ${tag}`);
  await box.press("Enter");

  // Live: the team's steps arrive one by one while it works.
  await expect(page.getByText("Checker: 6/10, sent back")).toBeVisible();
  const card = page.getByRole("article", { name: new RegExp(`launch ${tag}`) });
  await expect(card).toContainText("9/10", { timeout: 20_000 }); // the whole writing team runs first
  await expect(card).toContainText("(fake Humanizer)");

  await page.getByRole("button", { name: "▸ Show work" }).click();
  for (const label of ["Writer: first draft", "Writer: revision 1", "Humanizer: made it sound like you", "Final check: 9/10, ready"]) {
    await expect(page.getByText(label)).toBeVisible();
  }
  await expect(page.getByText("Make the first line about the result.")).toBeVisible(); // the Checker's note
  await page.getByText("See the text").first().click();
  await expect(page.getByText(`(fake Writer) A short post about launch ${tag}`)).toBeVisible();
});

test("asking for ideas saves them and shows them in Show work", async ({ page }, info) => {
  const tag = `${info.project.name}-${Date.now()}`;
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill(`ideas ${tag}`);
  await box.press("Enter");
  await page.getByRole("button", { name: "▸ Show work" }).click();
  await expect(page.getByText("Asking the Social Media Manager")).toBeVisible();
  await expect(page.getByText("Saved 3 ideas to your list")).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: `Fake idea 1: ${tag}` }).last()).toBeVisible();
});

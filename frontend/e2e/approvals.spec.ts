import { expect, test, type Page } from "@playwright/test";

async function draftInChat(page: Page, text: string) {
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill(`draft ${text}`);
  await box.press("Enter");
  const card = page.getByRole("article", { name: new RegExp(text.slice(0, 20)) });
  await expect(card.getByTestId("approval-status")).toHaveText("Waiting for you", { timeout: 30000 });
  return card;
}

test("approving in the chat updates the Approvals page, and the other way round", async ({ page }, info) => {
  test.setTimeout(60000); // the first fake-AI draft also loads the writing agents on a cold backend
  const tag = `${info.project.name}-${Date.now()}`;
  await page.goto("/");

  // Chat → Approvals page
  const first = await draftInChat(page, `First post ${tag}`);
  await expect(first.getByRole("link", { name: /Open LinkedIn/ })).toHaveAttribute("href", /linkedin\.com/);
  await first.getByRole("button", { name: "Edit" }).click();
  await first.getByRole("textbox", { name: "Edit draft" }).fill(`First post ${tag}, edited`);
  await first.getByRole("button", { name: "Save" }).click();
  await expect(first.getByText("Edited 1×.")).toBeVisible();
  await first.getByRole("button", { name: "Mark as posted" }).click();
  await expect(first.getByTestId("approval-status")).toHaveText("Posted");
  const chatUrl = page.url();

  await page.goto("/approvals");
  await page.getByRole("tab", { name: "Posted" }).click();
  await expect(page.getByText(`First post ${tag}, edited`)).toBeVisible();

  // Approvals page → chat
  await page.goto(chatUrl);
  await draftInChat(page, `Second post ${tag}`);
  await page.goto("/approvals");
  const second = page.getByRole("article", { name: new RegExp(`Second post ${tag}`) });
  await second.getByRole("button", { name: "Reject" }).click();
  await expect(second).toHaveCount(0); // it leaves the Waiting tab

  await page.goto(chatUrl);
  await expect(
    page.getByRole("article", { name: new RegExp(`Second post ${tag}`) }).getByTestId("approval-status"),
  ).toHaveText("Rejected");
});

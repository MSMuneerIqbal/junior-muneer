import { expect, test, type Page } from "@playwright/test";

// In FAKE_AI mode a fake Facebook Page is "connected": nothing leaves the PC.
async function draftForFacebook(page: Page, text: string) {
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill(`draft facebook ${text}`);
  await box.press("Enter");
  // Match the card by its exact title (the text may contain brackets like "[fail]").
  const card = page.getByRole("article", { name: `Facebook post: ${text}` });
  await expect(card.getByTestId("approval-status")).toHaveText("Waiting for you");
  return card;
}

test("approve & post sends it once, with a link to the post", async ({ page }, info) => {
  const tag = `${info.project.name}-${Date.now()}`;
  await page.goto("/");
  const card = await draftForFacebook(page, `Launch day ${tag}`);
  await card.getByRole("button", { name: "Approve & post" }).click();
  await expect(card.getByTestId("approval-status")).toHaveText("Posted");
  await expect(card.getByRole("link", { name: "View post ↗" })).toHaveAttribute("href", /example\.invalid\/fake-posts\/\d+/);
  await expect(card.getByRole("button", { name: /Post now|Approve/ })).toHaveCount(0);
});

test("a refused post says why and can be tried again on purpose", async ({ page }, info) => {
  const tag = `${info.project.name}-${Date.now()}`;
  await page.goto("/");
  const card = await draftForFacebook(page, `[fail] Refused ${tag}`);
  await card.getByRole("button", { name: "Approve & post" }).click();
  await expect(card.getByText(/Not posted: .*refused it/)).toBeVisible();
  await expect(card.getByTestId("approval-status")).toHaveText("Approved");
  await expect(card.getByRole("button", { name: "Try again" })).toBeVisible();
});

test("an unclear result asks you to check, and you say whether it posted", async ({ page }, info) => {
  const tag = `${info.project.name}-${Date.now()}`;
  await page.goto("/");
  const card = await draftForFacebook(page, `[unclear] Maybe ${tag}`);
  await card.getByRole("button", { name: "Approve & post" }).click();
  await expect(card.getByText("We couldn't tell if it was posted.")).toBeVisible();
  await expect(card.getByTestId("approval-status")).toHaveText("Check manually");
  await card.getByRole("button", { name: "It's posted" }).click();
  await expect(card.getByTestId("approval-status")).toHaveText("Posted");
});

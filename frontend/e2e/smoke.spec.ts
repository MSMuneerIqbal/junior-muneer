import { expect, test, type Page } from "@playwright/test";

async function openMenu(page: Page) {
  const menu = page.getByRole("button", { name: "Open chats and menu" });
  if (await menu.isVisible()) await menu.click();
}

test("chat page loads, sends a message and streams the answer", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("What's on your mind?")).toBeVisible();

  const box = page.getByLabel("Message");
  await box.fill("Hello from the smoke test");
  await box.press("Enter");

  // The answer streams in, then gets its Show work panel.
  await expect(page.getByText("(fake AI) You said:")).toBeVisible();
  await expect(page.getByText("Show work")).toBeVisible();
  await expect(page).toHaveURL(/\?c=\d+/);

  // It's saved: a reload shows it again, and the chat is in the sidebar.
  await page.reload();
  await expect(page.locator("main").getByText("Hello from the smoke test").first()).toBeVisible();
  await openMenu(page);
  await expect(page.getByRole("link", { name: "Hello from the smoke test" }).first()).toBeVisible();
});

test("Urdu reads right to left", async ({ page }) => {
  await page.goto("/");
  const box = page.getByLabel("Message");
  await box.fill("آپ کیسے ہیں؟");
  await box.press("Enter");
  await expect(page.getByText("Show work")).toBeVisible();
  const bubble = page.locator("main").getByText("آپ کیسے ہیں؟").first();
  expect(await bubble.evaluate((el) => getComputedStyle(el).direction)).toBe("rtl");
});

test("memory note can be undone", async ({ page }) => {
  await page.goto("/");
  const box = page.getByLabel("Message");
  await box.fill("remember I drink green tea");
  await box.press("Enter");
  await expect(page.getByText("Memory updated: I drink green tea")).toBeVisible();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("Undone")).toBeVisible();

  await openMenu(page);
  await page.getByRole("link", { name: "Memory", exact: true }).click();
  const main = page.locator("main");
  await expect(main.getByRole("heading", { name: "Memory" })).toBeVisible();
  await expect(main.getByText("I drink green tea")).toHaveCount(0);
});

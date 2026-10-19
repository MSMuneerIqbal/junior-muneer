import { expect, test, type Page } from "@playwright/test";

async function openMenu(page: Page) {
  const menu = page.getByRole("button", { name: "Open chats and menu" });
  if (await menu.isVisible()) await menu.click();
}

test("the sidebar: New chat and features on top, your chats under Recents, you at the bottom", async ({ page }) => {
  const tag = Date.now().toString(36);
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill(`Sidebar test ${tag}`);
  await box.press("Enter");
  await expect(page.getByText("Show work")).toBeVisible();

  await openMenu(page);
  const main = page.getByRole("navigation", { name: "Main" });
  await expect(main.getByRole("link", { name: "New chat" })).toBeVisible();
  await expect(main.getByRole("link", { name: "Inbox" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recents" })).toBeVisible();
  await expect(page.getByRole("link", { name: `Sidebar test ${tag}` })).toBeVisible();

  // Search filters the chats.
  await page.getByRole("button", { name: "Search chats" }).click();
  await page.getByRole("searchbox", { name: "Search text" }).fill(tag);
  await expect(page.getByRole("heading", { name: "Search results" })).toBeVisible();
  await expect(page.getByRole("link", { name: `Sidebar test ${tag}` })).toBeVisible();

  // Your menu: Profile, Settings, Theme.
  await page.getByRole("button", { name: "Open your menu" }).click();
  const menu = page.getByRole("menu", { name: "Your menu" });
  await expect(menu.getByRole("menuitem", { name: "Profile" })).toBeVisible();
  await expect(menu.getByRole("menuitem", { name: /Theme/ })).toBeVisible();
  await menu.getByRole("menuitem", { name: "Profile" }).click();
  await expect(page).toHaveURL(/\/profile$/);
});

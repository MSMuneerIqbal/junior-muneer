import { expect, test } from "@playwright/test";

test("a long request runs in the background: keep chatting, the result appears in the chat", async ({ page }, info) => {
  const tag = `${info.project.name}-${Date.now().toString(36)}`;
  await page.goto("/");
  await page.getByRole("textbox", { name: "Message" }).fill(`in background: 3 LinkedIn posts ${tag}`);
  await page.getByRole("textbox", { name: "Message" }).press("Enter");

  await expect(page.getByText("(fake AI) I'm on it in the background.")).toBeVisible({ timeout: 15_000 });
  const working = page.getByRole("status").filter({ hasText: `Working on it in the background: 3 LinkedIn posts ${tag}` });
  await expect(working).toBeVisible();

  // You can keep chatting while it works.
  await page.getByRole("textbox", { name: "Message" }).fill(`hello while it works ${tag}`);
  await page.getByRole("textbox", { name: "Message" }).press("Enter");
  await expect(page.getByText(`hello while it works ${tag}`).last()).toBeVisible();

  // The result is posted to the same chat.
  await expect(page.getByText(`(fake AI) Finished in the background: 3 LinkedIn posts ${tag}`)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Done in the background: 3 LinkedIn posts").last()).toBeVisible();
  await expect(working).toHaveCount(0);

  if (info.project.name === "desktop") {
    const box = page.getByRole("region", { name: "Background work" });
    await expect(box.getByRole("listitem").filter({ hasText: `3 LinkedIn posts ${tag}` })).toContainText("done");
  }
});

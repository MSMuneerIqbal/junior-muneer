import { expect, test } from "@playwright/test";

test("an Upwork draft that breaks Upwork's rules is flagged before you copy it", async ({ page, request }, info) => {
  const tag = `${info.project.name}-${Date.now().toString(36)}`; // no long digit runs (they look like phone numbers)
  await request.post("http://127.0.0.1:8100/api/approvals", {
    data: { platform: "upwork", item_type: "message", text: `Thanks ${tag}! WhatsApp me on +92 300 1234567 and we can start.` },
  });
  await page.goto("/approvals");
  const card = page.getByRole("article", { name: new RegExp(`Thanks ${tag}`) });
  const warning = card.getByRole("alert", { name: "Upwork's rules" });
  await expect(warning).toContainText("Mentions WhatsApp");
  await expect(warning).toContainText("phone number");
  await expect(card.getByRole("button", { name: "Copy anyway" })).toBeVisible();

  // Fix it: the warning goes away.
  await card.getByRole("button", { name: "Edit" }).click();
  await card.getByRole("textbox", { name: "Edit draft" }).fill(`Thanks ${tag}! Happy to start here on Upwork.`);
  await card.getByRole("button", { name: "Save" }).click();
  await expect(card.getByRole("alert", { name: "Upwork's rules" })).toHaveCount(0);
  await expect(card.getByRole("button", { name: "Copy", exact: true })).toBeVisible();
  await card.getByRole("button", { name: "Mark as sent" }).click();
  await expect(card).toHaveCount(0); // sent: it leaves the Waiting tab
});

import { expect, test, type Page } from "@playwright/test";

async function pasteAndAsk(page: Page, text: string, link: string, ask: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Paste from another site" }).click();
  const box = page.getByRole("region", { name: "Paste box" });
  await box.getByRole("textbox", { name: "Pasted text" }).fill(text);
  await box.getByRole("textbox", { name: "Link (optional)" }).fill(link);
  await page.getByRole("textbox", { name: "Message" }).fill(ask);
  await page.getByRole("textbox", { name: "Message" }).press("Enter");
}

test("the Freelance page shows your jobs and orders, and you can update an order", async ({ page, request }, info) => {
  await request.put("http://127.0.0.1:8100/api/profile", { data: { headline: "AI engineer", proof: ["Built chatbots"] } });
  test.setTimeout(60_000); // two chat turns, then the page
  const tag = `${info.project.name}-${Date.now().toString(36)}`;

  await pasteAndAsk(page, `Clinic bot ${tag}\nWe need a chatbot. Budget $400.`, "https://www.upwork.com/jobs/~01pagetest", "Should I apply?");
  await expect(page.getByText(/scored 8\/10/).first()).toBeVisible({ timeout: 20_000 });
  await pasteAndAsk(page, `Order page ${tag}\nDue in 20 hours.`, "https://www.fiverr.com/users/m/manage_orders/FOPAGE", "Track this order");
  await expect(page.getByText(/Order \d+ saved/).first()).toBeVisible({ timeout: 20_000 });

  await page.goto("/freelance");
  await expect(page.getByRole("heading", { name: "Freelance", level: 1 })).toBeVisible();

  // Upwork: the scored job, with a button that asks for its proposal.
  const job = page.getByRole("listitem", { name: new RegExp(`Clinic bot ${tag}`) });
  await expect(job).toContainText("8/10 · apply");
  await expect(job.getByRole("link", { name: "Write a proposal" })).toHaveAttribute("href", /Write%20the%20proposal%20for%20job%20\d+/);

  // Fiverr: the open order, due within a day; mark it delivered and it moves to Finished.
  await page.getByRole("tab", { name: "Fiverr" }).click();
  const open = page.getByRole("region", { name: "Orders to deliver" });
  const order = open.getByRole("listitem", { name: new RegExp(`Order page ${tag}`) });
  await expect(order).toContainText(/in (19|20) h/);
  await expect(order.getByRole("link", { name: "Write delivery message" })).toHaveAttribute("href", /delivery%20message%20for%20order/);
  await order.getByRole("button", { name: "Mark delivered" }).click();
  await expect(order).toHaveCount(0);
  const done = page.getByRole("region", { name: "Finished orders" }).getByRole("listitem", { name: new RegExp(`Order page ${tag}`) });
  await expect(done).toContainText("Delivered");
});

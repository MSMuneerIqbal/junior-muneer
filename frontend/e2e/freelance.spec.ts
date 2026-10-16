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

test("paste a job post and get a scored proposal, ready to copy into Upwork", async ({ page, request }, info) => {
  await request.put("http://127.0.0.1:8100/api/profile", {
    data: { headline: "AI engineer", proof: ["Built chatbots in English and Urdu"] },
  });
  const tag = `${info.project.name}-${Date.now().toString(36)}`;
  await page.goto("/");
  await page.getByRole("button", { name: "Paste from another site" }).click();
  const box = page.getByRole("region", { name: "Paste box" });
  await box
    .getByRole("textbox", { name: "Pasted text" })
    .fill(`Clinic chatbot ${tag}\nWe need a chatbot for patients. Budget $500.\nScreening question: Which chatbot did you build ${tag}?`);
  await box.getByRole("textbox", { name: "Link (optional)" }).fill("https://www.upwork.com/jobs/~01testjob");
  await expect(box.getByRole("combobox", { name: "Type" })).toHaveValue("job");
  await page.getByRole("textbox", { name: "Message" }).fill("Write a proposal for this job");
  await page.getByRole("textbox", { name: "Message" }).press("Enter");

  const card = page.getByRole("article", { name: /Upwork proposal/ }).last();
  await expect(card).toBeVisible({ timeout: 20_000 }); // scoring + the writing team
  await expect(card.getByRole("link", { name: "Open the job ↗" })).toHaveAttribute("href", "https://www.upwork.com/jobs/~01testjob");
  // The screening answer is on the same card, in its own box with its own Copy button.
  const answers = card.getByRole("region", { name: "Screening answers" });
  await expect(answers).toContainText(`Which chatbot did you build ${tag}?`);
  await expect(answers.getByRole("button", { name: "Copy answer 1" })).toBeVisible();
  await expect(page.getByRole("article", { name: /Upwork proposal/ })).toHaveCount(1);
  await page.getByRole("button", { name: "▸ Show work" }).last().click();
  await expect(page.getByText(/Job \d+ scored 8\/10: apply/)).toBeVisible();

  await card.getByRole("button", { name: "Mark as sent" }).click();
  await expect(card.getByTestId("approval-status")).toHaveText("Sent");
});

test("paste a client conversation and get a reply to copy, with warning signs flagged", async ({ page }, info) => {
  const tag = `${info.project.name}-${Date.now().toString(36)}`;
  const room = "https://www.upwork.com/ab/messages/rooms/room_test";
  await page.goto("/");
  await page.getByRole("button", { name: "Paste from another site" }).click();
  const box = page.getByRole("region", { name: "Paste box" });
  await box.getByRole("textbox", { name: "Pasted text" }).fill(`Sarah ${tag}: Can you add voice replies? Let's continue on WhatsApp.`);
  await box.getByRole("textbox", { name: "Link (optional)" }).fill(room);
  await expect(box.getByRole("combobox", { name: "Type" })).toHaveValue("client_message"); // guessed from the link
  await page.getByRole("textbox", { name: "Message" }).fill("Reply to this client");
  await page.getByRole("textbox", { name: "Message" }).press("Enter");

  const card = page.getByRole("article", { name: /Upwork reply/ });
  await expect(card).toBeVisible({ timeout: 20_000 });
  await expect(card.getByRole("note", { name: "Warning signs from the client" })).toContainText("outside the platform");
  await expect(card.getByRole("link", { name: "Open the conversation ↗" })).toHaveAttribute("href", room);
  await expect(card.getByRole("button", { name: "📅 Plan" })).toHaveCount(0); // posting times and images are for posts
  await expect(card.getByLabel("Add image")).toHaveCount(0);
  await page.getByRole("button", { name: "▸ Show work" }).last().click();
  await expect(page.getByText("Warning signs in the client's message")).toBeVisible();

  await card.getByRole("button", { name: "Mark as sent" }).click();
  await expect(card.getByTestId("approval-status")).toHaveText("Sent");
  await expect(card.getByRole("note", { name: "Warning signs from the client" })).toHaveCount(0); // sent: no longer needed
});

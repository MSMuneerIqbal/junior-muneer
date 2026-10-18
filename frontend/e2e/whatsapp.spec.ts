import { createHmac } from "node:crypto";
import { expect, test } from "@playwright/test";

test("a WhatsApp message lands in your chat history, answered, with 🟢 in the chat list", async ({ page, request }, info) => {
  const tag = `${info.project.name}-${Date.now().toString(36)}`;
  const body = JSON.stringify({
    object: "whatsapp_business_account",
    entry: [{ changes: [{ value: { messages: [{ from: "923001112233", id: `wamid.${tag}`, type: "text", text: { body: `Salam from WhatsApp ${tag}` } }] } }] }],
  });
  const signature = "sha256=" + createHmac("sha256", "e2e-secret").update(body).digest("hex");
  const r = await request.post("http://127.0.0.1:8100/api/whatsapp/webhook", {
    data: body,
    headers: { "content-type": "application/json", "x-hub-signature-256": signature },
  });
  expect(r.ok()).toBeTruthy();

  // Someone else's message (not signed by Meta) is refused.
  const forged = await request.post("http://127.0.0.1:8100/api/whatsapp/webhook", {
    data: body,
    headers: { "content-type": "application/json", "x-hub-signature-256": "sha256=00" },
  });
  expect(forged.status()).toBe(403);

  // Saved in a WhatsApp chat, answered by Junior Muneer.
  let chatId = 0;
  await expect(async () => {
    const chats = (await (await request.get("http://127.0.0.1:8100/api/conversations")).json()) as { id: number; kind: string }[];
    chatId = chats.find((c) => c.kind === "whatsapp")?.id ?? 0;
    expect(chatId).toBeGreaterThan(0);
  }).toPass({ timeout: 15_000 });
  await page.goto(`/?c=${chatId}`);
  await expect(page.getByText(`Salam from WhatsApp ${tag}`).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("(fake AI) You said:").first()).toBeVisible({ timeout: 15_000 });
  if (info.project.name === "desktop") {
    await expect(page.getByRole("link", { name: /WhatsApp · / }).first()).toContainText("🟢"); // in your chat list
  }
});

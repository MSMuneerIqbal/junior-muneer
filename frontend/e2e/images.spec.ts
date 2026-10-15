import { expect, test } from "@playwright/test";

// A 1×1 PNG.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

test("an Instagram draft waits for an image, then can be posted", async ({ page, request }, info) => {
  const tag = `${info.project.name}-${Date.now()}`;
  await request.post("http://127.0.0.1:8100/api/approvals", {
    data: { platform: "instagram", item_type: "post", text: `Caption ${tag}` },
  });
  await page.goto("/approvals");
  const card = page.getByRole("article", { name: new RegExp(`Caption ${tag}`) });
  await expect(card.getByText("Instagram posts need an image")).toBeVisible();
  await expect(card.getByRole("button", { name: "Mark as posted" })).toBeDisabled();

  await card.getByLabel("Add image").setInputFiles({ name: "shot.png", mimeType: "image/png", buffer: PNG });
  await expect(card.getByRole("img", { name: "shot.png" })).toBeVisible();
  await expect(card.getByText("Instagram posts need an image")).toHaveCount(0);

  // Remove and add again: the warning comes and goes.
  await card.getByRole("button", { name: "Remove shot.png" }).click();
  await expect(card.getByText("Instagram posts need an image")).toBeVisible();
  await card.getByLabel("Add image").setInputFiles({ name: "photo.png", mimeType: "image/png", buffer: PNG });
  await card.getByRole("button", { name: "Mark as posted" }).click();
  await expect(card).toHaveCount(0); // posted: it leaves the Waiting tab
});

test("a file that isn't an image is refused with a clear message", async ({ page, request }, info) => {
  const tag = `${info.project.name}-${Date.now()}`;
  await request.post("http://127.0.0.1:8100/api/approvals", {
    data: { platform: "linkedin", item_type: "post", text: `Post ${tag}` },
  });
  await page.goto("/approvals");
  const card = page.getByRole("article", { name: new RegExp(`Post ${tag}`) });
  await card.getByLabel("Add image").setInputFiles({ name: "notes.png", mimeType: "image/png", buffer: Buffer.from("not an image") });
  await expect(card.getByRole("alert")).toContainText("Only JPEG, PNG, WebP or GIF");
});

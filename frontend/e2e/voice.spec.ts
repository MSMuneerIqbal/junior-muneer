import { expect, test } from "@playwright/test";

test("hold the mic, release, and the voice message is sent and answered", async ({ page }) => {
  await page.goto("/");
  const mic = page.getByRole("button", { name: "Record a voice message" });
  await expect(mic).toBeVisible();

  const box = await mic.boundingBox();
  if (!box) throw new Error("mic button not visible");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await expect(page.getByText(/release to send/)).toBeVisible();
  await page.waitForTimeout(1500);
  await page.mouse.up();

  // The fake speech-to-text describes the recording; it's sent like a typed message.
  const main = page.locator("main");
  await expect(main.getByText(/fake transcription of a \d+-byte recording/).first()).toBeVisible();
  await expect(main.getByLabel("Your voice message")).toBeVisible(); // playable recording
  await expect(page.getByText("Show work")).toBeVisible();
  await expect(page.getByRole("button", { name: /Read aloud|Stop reading aloud/ })).toBeVisible();
});

test("too short a press asks you to hold", async ({ page }) => {
  await page.goto("/");
  const mic = page.getByRole("button", { name: "Record a voice message" });
  const box = await mic.boundingBox();
  if (!box) throw new Error("mic button not visible");
  // A quick tap starts tap-to-talk; a second quick tap stops it almost at once.
  await mic.click();
  await page.waitForTimeout(200);
  await page.getByRole("button", { name: "Stop and send voice message" }).click();
  await expect(page.getByText("Too short. Hold the mic button while you speak.")).toBeVisible();
});

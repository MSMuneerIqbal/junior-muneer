import { expect, test } from "@playwright/test";

test("hold the mic, release, and the voice message is sent and answered", async ({ page }) => {
  await page.goto("/");
  const mic = page.getByRole("button", { name: "Record a voice message" });
  await expect(mic).toBeVisible();

  await expect(mic).toBeEnabled();
  // Locator hover waits for a stable position; a cached bounding box can miss the mic as mobile layout settles.
  await mic.hover();
  await page.mouse.down();
  await expect(page.getByText(/release to send/)).toBeVisible();
  await page.waitForTimeout(1500);
  await page.mouse.up();

  // The fake speech-to-text describes the recording; it's sent like a typed message.
  const main = page.locator("main");
  // Transcribe, answer and speak can take a while late in a long test run.
  await expect(main.getByText(/fake transcription of a \d+-byte recording/).first()).toBeVisible({ timeout: 20_000 });
  await expect(main.getByLabel("Your voice message")).toBeVisible(); // playable recording
  await expect(page.getByText("Show work")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: /Read aloud|Stop reading aloud/ })).toBeVisible();
});

test("too short a press asks you to hold", async ({ page }) => {
  await page.goto("/");
  const mic = page.getByRole("button", { name: "Record a voice message" });
  const box = await mic.boundingBox();
  if (!box) throw new Error("mic button not visible");
  // A quick tap starts tap-to-talk; a second tap stops it the moment recording starts
  // (clicked from inside the page, so a busy test machine doesn't stretch the gap).
  await mic.click();
  await page.getByRole("button", { name: "Stop and send voice message" }).waitFor();
  await page.evaluate(() => {
    const b = document.querySelector<HTMLButtonElement>('[aria-label="Stop and send voice message"]');
    b?.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    b?.dispatchEvent(new PointerEvent("pointerup", { bubbles: true }));
  });
  await expect(page.getByText("Too short. Hold the mic button while you speak.")).toBeVisible();
});

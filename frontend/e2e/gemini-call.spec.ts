import { expect, test } from "@playwright/test";

const BACKEND = "http://127.0.0.1:8100";

test("a live call with Gemini Live: the microphone streams, he answers, the call is saved", async ({ page, request }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "one shared database: once is enough");
  await request.patch(`${BACKEND}/api/settings`, { data: { voice_provider_model: "gemini-3.8-live" } });
  try {
    await page.goto("/");
    await page.getByRole("button", { name: "Live call" }).click();
    const call = page.getByRole("dialog", { name: "Live call" });
    // The fake microphone streams to the backend; the pretend Gemini hears it and answers.
    await expect(call.getByText("(fake Gemini) Walaikum salam! Kya haal hai?").first()).toBeVisible({ timeout: 20_000 });
    await expect(call.getByText("Assalam o alaikum").first()).toBeVisible();
    await call.getByRole("button", { name: "End call" }).click();
    await expect(call.getByRole("status")).toHaveText(/Call ended/);
  } finally {
    await request.patch(`${BACKEND}/api/settings`, { data: { voice_provider_model: "openai-realtime" } });
  }
});

test("Settings: the voice engine and Gemini's voice", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "one shared database: once is enough");
  await page.goto("/settings#calls");
  const engine = page.getByRole("radiogroup", { name: "Voice engine" });
  await expect(engine.getByRole("radio", { name: /OpenAI Realtime/ })).toHaveAttribute("aria-checked", "true");
  await engine.getByRole("radio", { name: /Gemini 3\.8 Live/ }).click();
  const voices = page.getByRole("radiogroup", { name: "Gemini voice" });
  await expect(voices.getByRole("radio", { name: /Charon/ })).toHaveAttribute("aria-checked", "true");
  await voices.getByRole("radio", { name: /Kore/ }).click();
  await expect(voices.getByRole("radio", { name: /Kore/ })).toHaveAttribute("aria-checked", "true");
  // ▶ plays a sample the pretend Gemini makes (a WAV from the backend).
  const sample = page.waitForResponse((r) => r.url().includes("/api/voice/gemini-preview/Puck.wav"));
  await voices.getByRole("button", { name: "Play a sample of Puck" }).click();
  expect((await sample).headers()["content-type"]).toContain("audio/wav");
  await page.getByRole("button", { name: "Discard" }).click();
});

test("Settings: voice messages can use Gemini, with Gemini's voices", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "one shared database: once is enough");
  await page.goto("/settings#voice");
  const engine = page.getByRole("radiogroup", { name: "Voice messages engine" });
  await expect(engine.getByRole("radio", { name: /OpenAI/ })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("radiogroup", { name: "His voice" })).toBeVisible();
  await engine.getByRole("radio", { name: /Gemini/ }).click();
  await expect(page.getByRole("radiogroup", { name: "Gemini voice" })).toBeVisible();
  await expect(page.getByRole("radiogroup", { name: "His voice" })).toHaveCount(0);
  await page.getByRole("button", { name: "Discard" }).click();
});

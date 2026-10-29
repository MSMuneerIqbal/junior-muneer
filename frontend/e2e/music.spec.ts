import { expect, test } from "@playwright/test";

test.afterEach(async ({ request }) => {
  await request.put("http://127.0.0.1:8100/api/permissions/mode", { data: { mode: "rules" } });
  await request.put("http://127.0.0.1:8100/api/computer/browser", { data: { enabled: false, sites: [] } });
});

for (const mode of ["rules", "ask_all"] as const) {
  test(`YouTube music ${mode === "rules" ? "plays in Auto" : "starts after one Manual approval"}`, async ({ page, request }) => {
    test.setTimeout(90_000); // Play, change and stop each wait for a separate completed action.
    await request.put("http://127.0.0.1:8100/api/computer/browser", { data: { enabled: true, sites: ["*"] } });
    await request.put("http://127.0.0.1:8100/api/permissions/mode", { data: { mode } });
    await page.goto("/");
    const input = page.getByRole("textbox", { name: "Message" });
    await input.fill("song play kro yr blue eyes yo yo honey sing wala");
    await input.press("Enter");
    const card = page.getByRole("article").filter({ hasText: "Play on YouTube" });
    if (mode === "ask_all") {
      await expect(card.getByTestId("approval-status")).toHaveText("Waiting for you", { timeout: 30_000 });
      await card.getByRole("button", { name: "Approve & run", exact: true }).click();
    }
    await expect(card.getByTestId("approval-status")).toHaveText("Done", { timeout: 30_000 });
    await expect(card).toHaveCount(1);
    await input.fill("song change kro");
    await input.press("Enter");
    const change = page.getByRole("article").filter({ hasText: "Play the next YouTube video" });
    if (mode === "ask_all") {
      await expect(change.getByTestId("approval-status")).toHaveText("Waiting for you", { timeout: 30_000 });
      await change.getByRole("button", { name: "Approve & run", exact: true }).click();
    }
    await expect(change.getByTestId("approval-status")).toHaveText("Done", { timeout: 30_000 });
    await input.fill("stop the song");
    await input.press("Enter");
    const stop = page.getByRole("article").filter({ hasText: "Stop Junior's YouTube player" });
    if (mode === "ask_all") {
      await expect(stop.getByTestId("approval-status")).toHaveText("Waiting for you", { timeout: 30_000 });
      await stop.getByRole("button", { name: "Approve & run", exact: true }).click();
    }
    await expect(stop.getByTestId("approval-status")).toHaveText("Done", { timeout: 30_000 });
  });
}

import { expect, test } from "@playwright/test";

test("Skills in Settings: create, use in chat, edit, preserve unsaved work and delete", async ({ page }, info) => {
  test.setTimeout(75_000); // two streamed chats plus create/edit/delete and reloads on a cold Windows build
  const name = `test_${info.project.name}_${Date.now()}`;
  const label = name.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
  await page.goto("/settings");
  if (info.project.name === "phone") {
    await page.getByRole("combobox", { name: "Settings section" }).selectOption("skills");
  } else {
    await page.getByRole("navigation", { name: "Settings sections" }).getByRole("button", { name: "Skills", exact: true }).click();
  }
  const section = page.getByRole("region", { name: "Skills", exact: true });
  await expect(section).toBeVisible();
  await expect(page).toHaveURL(/#skills$/);
  await expect(section.getByRole("heading", { name: "Daily priorities" })).toBeVisible();
  await page.screenshot({ path: `test-results/skills-${info.project.name}.png`, fullPage: true });
  await section.getByRole("button", { name: "Add skill" }).click();
  await section.getByLabel("Skill name", { exact: true }).fill(name);
  await section.getByLabel("When to use it", { exact: true }).fill("Use when I ask for a test report from supplied notes.");
  await section.getByLabel("Instructions", { exact: true }).fill("Read the supplied notes and return the marker skill-original-proof. Do not take any actions.");
  await section.getByRole("button", { name: "Save skill", exact: true }).click();
  await expect(section.getByRole("status")).toContainText("saved");
  await page.reload();
  await expect(section.getByRole("button", { name: `Edit ${label}`, exact: true })).toBeVisible();

  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill(`use skill ${name}`);
  await box.press("Enter");
  await expect(page.getByText(/skill-original-proof/).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Show work").first()).toBeVisible();

  await page.goto("/settings#skills");
  await section.getByRole("button", { name: `Edit ${label}`, exact: true }).click();
  await section.getByLabel("Instructions", { exact: true }).fill("Read the supplied notes and return the marker skill-edited-proof. Keep every fact accurate.");
  await section.getByRole("button", { name: "Back to skills" }).click();
  await expect(section.getByRole("group", { name: "Unsaved skill changes" })).toBeVisible();
  await section.getByRole("button", { name: "Keep editing" }).click();
  await section.getByRole("button", { name: "Save skill", exact: true }).click();
  await expect(section.getByRole("status")).toContainText("saved");

  await page.goto("/");
  await box.fill(`use skill ${name}`);
  await box.press("Enter");
  await expect(page.getByText(/skill-edited-proof/).first()).toBeVisible({ timeout: 30_000 });
  await page.goto("/settings#skills");
  await section.getByRole("button", { name: `Edit ${label}`, exact: true }).click();
  await section.getByRole("button", { name: "Delete skill", exact: true }).click();
  await section.getByRole("button", { name: "Keep skill" }).click();
  await expect(section.getByRole("group", { name: "Confirm skill deletion" })).toHaveCount(0);
  await section.getByRole("button", { name: "Delete skill", exact: true }).click();
  await section.getByRole("button", { name: "Confirm delete", exact: true }).click();
  await expect(section.getByRole("status")).toContainText("deleted");
  await page.reload();
  await expect(section.getByRole("button", { name: "Add skill" })).toBeVisible();
  await expect(section.getByRole("button", { name: `Edit ${label}`, exact: true })).toHaveCount(0);
});

test("Skills show a server validation error without losing the editor", async ({ page }, info) => {
  await page.goto("/settings#skills");
  const section = page.getByRole("region", { name: "Skills", exact: true });
  await section.getByRole("button", { name: "Add skill" }).click();
  await section.getByLabel("Skill name", { exact: true }).fill("daily_priorities");
  await section.getByLabel("When to use it", { exact: true }).fill("An accidentally duplicated daily priorities skill.");
  await section.getByLabel("Instructions", { exact: true }).fill("Read the user's supplied notes and make a concise plan without inventing any deadlines.");
  await section.getByRole("button", { name: "Save skill", exact: true }).click();
  await expect(section.getByRole("alert")).toContainText("already exists");
  await expect(section.getByLabel("Instructions", { exact: true })).toHaveValue(/without inventing/);
  await page.screenshot({ path: `test-results/skills-editor-${info.project.name}.png`, fullPage: true });
});

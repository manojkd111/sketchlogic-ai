import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const whiteboard = path.join(__dirname, "fixtures", "whiteboard.png");

// App alerts only: Next renders its own (empty) role="alert" route announcer on every page.
const appAlert = (page: Page) => page.locator("[role=alert]:not(#__next-route-announcer__)");

test("upload → validation → extract → review in editor → save survives reload", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText(/API ok/)).toBeVisible();

  await page.getByLabel("Choose file").setInputFiles(whiteboard);
  // Backend validation result (sniffed type and decoded dimensions), consent off by default.
  await expect(page.getByText("800 × 450px")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /improve the model/i })).not.toBeChecked();

  await page.getByRole("button", { name: "Upload" }).click();
  await page.getByRole("button", { name: "Extract diagram" }).click();
  await page.getByRole("link", { name: "Open in editor" }).click();

  await expect(page).toHaveURL(/\/graphs\/graph-[0-9a-f]{32}$/);
  await expect(page.locator(".react-flow__node")).toHaveCount(3);
  await expect(page.getByText("1 inferred to review")).toBeVisible();

  const review = page.getByRole("region", { name: /review inferred connections/i });
  await expect(review.getByText("Adjacent boxes with no visible arrow.")).toBeVisible();
  await review.getByRole("button", { name: /^Accept inferred connection/ }).click();
  await expect(review.getByText("Nothing to review.")).toBeVisible();

  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved version 2.")).toBeVisible();

  await page.reload();
  await expect(page.locator(".react-flow__node")).toHaveCount(3);
  await expect(page.getByText("v2", { exact: true })).toBeVisible();
  await expect(page.getByText(/inferred to review/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
});

test("the backend rejects a file whose bytes don't match its name", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Choose file").setInputFiles({
    name: "looks-like.png",
    mimeType: "image/png",
    buffer: Buffer.concat([Buffer.from("GIF89a"), Buffer.alloc(64)]),
  });
  await expect(appAlert(page)).toContainText(/unsupported/i);
  await expect(page.getByRole("button", { name: "Upload" })).toHaveCount(0);
});

test("a sketch goes from the canvas to the editor", async ({ page }) => {
  await page.goto("/sketch");
  const use = page.getByRole("button", { name: "Use this sketch" });
  await expect(use).toBeEnabled({ timeout: 60_000 });

  await use.click();
  await expect(appAlert(page)).toHaveText("Draw something first.");

  // Pick the rectangle tool from the toolbar (focus is on our button, so shortcuts would not
  // reach Excalidraw), then drag on the canvas.
  await page.getByTitle(/^Rectangle/).click();
  await expect(page.getByRole("radio", { name: "Rectangle" })).toBeChecked();
  await page.mouse.move(500, 350);
  await page.mouse.down();
  await page.mouse.move(700, 470, { steps: 10 });
  await page.mouse.up();

  await use.click();
  await page.getByRole("link", { name: "Open in editor" }).click();
  await expect(page).toHaveURL(/\/graphs\/graph-[0-9a-f]{32}$/);
  await expect(page.locator(".react-flow__node")).toHaveCount(3);
});

test("a spreadsheet is imported as an observed graph with groups and kinds", async ({ page }) => {
  await page.goto("/");
  await page
    .getByLabel("Choose file")
    .setInputFiles(path.join(__dirname, "fixtures", "services.xlsx"));
  await expect(page.getByText("Connections, Nodes")).toBeVisible();

  await page.getByRole("button", { name: "Upload" }).click();
  await page.getByRole("button", { name: "Extract diagram" }).click();
  await page.getByRole("link", { name: "Open in editor" }).click();

  await expect(page.getByRole("heading", { name: "services" })).toBeVisible();
  await expect(page.locator(".react-flow__node-graphNode")).toHaveCount(4);
  await expect(page.locator(".react-flow__node-graphGroup")).toHaveCount(1);
  await expect(page.getByText("Private subnet")).toBeVisible();
  // Imported connections are observed, so there is nothing to review.
  await expect(page.getByText("Nothing to review.")).toBeVisible();
  await expect(page.locator(".react-flow__node", { hasText: "Orders DB" })).toContainText(
    "database",
  );
});

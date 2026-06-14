import { test, expect } from "@playwright/test";

test.describe("New Project Modal", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("opens modal when clicking New Project button", async ({ page }) => {
    // Click the New Project button (in empty state or topbar)
    const newBtn = page.getByRole("button", { name: /new project/i });
    await newBtn.first().click();

    // Modal should be visible
    await expect(page.getByText("New Project")).toBeVisible();
    await expect(page.getByText("Project Brief")).toBeVisible();
  });

  test("can type a project title and brief", async ({ page }) => {
    // Open modal
    await page.getByRole("button", { name: /new project/i }).first().click();

    // Fill form
    await page.getByPlaceholder("My Awesome App").fill("Todo App");
    await page
      .getByPlaceholder("Describe the application you want to build...")
      .fill("Build a todo app with FastAPI and React");

    // Verify input values
    await expect(page.getByPlaceholder("My Awesome App")).toHaveValue("Todo App");
    await expect(
      page.getByPlaceholder("Describe the application you want to build...")
    ).toHaveValue("Build a todo app with FastAPI and React");
  });

  test("submit button disabled when prompt is empty", async ({ page }) => {
    await page.getByRole("button", { name: /new project/i }).first().click();
    const submitBtn = page.getByRole("button", { name: /create project/i });
    await expect(submitBtn).toBeDisabled();
  });

  test("submit button enables when prompt has text", async ({ page }) => {
    await page.getByRole("button", { name: /new project/i }).first().click();
    const submitBtn = page.getByRole("button", { name: /create project/i });
    await expect(submitBtn).toBeDisabled();

    await page
      .getByPlaceholder("Describe the application you want to build...")
      .fill("Build something");
    await expect(submitBtn).toBeEnabled();
  });

  test("closes modal on Cancel click", async ({ page }) => {
    await page.getByRole("button", { name: /new project/i }).first().click();
    await expect(page.getByText("New Project")).toBeVisible();

    await page.getByRole("button", { name: /cancel/i }).click();
    await expect(page.getByText("New Project")).not.toBeVisible();
  });

  test("closes modal on overlay click", async ({ page }) => {
    await page.getByRole("button", { name: /new project/i }).first().click();
    await expect(page.getByText("New Project")).toBeVisible();

    // Click the backdrop
    await page.locator(".backdrop-blur-sm").click();
    await expect(page.getByText("New Project")).not.toBeVisible();
  });

  test("shows character count for prompt textarea", async ({ page }) => {
    await page.getByRole("button", { name: /new project/i }).first().click();
    await expect(page.getByText("/2000")).toBeVisible();

    await page
      .getByPlaceholder("Describe the application you want to build...")
      .fill("Hello");
    await expect(page.getByText("5/2000")).toBeVisible();
  });

  test("submits project and navigates to detail page", async ({ page }) => {
    // Mock the API response
    await page.route("**/api/v1/projects", async (route) => {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          project_id: "test-proj-123",
          ws_url: "/ws/projects/test-proj-123",
          status: "pending",
        }),
      });
    });

    // Open modal and fill form
    await page.getByRole("button", { name: /new project/i }).first().click();
    await page.getByPlaceholder("My Awesome App").fill("Test App");
    await page
      .getByPlaceholder("Describe the application you want to build...")
      .fill("Build a test app");

    // Submit
    await page.getByRole("button", { name: /create project/i }).click();

    // Should navigate to project detail page
    await page.waitForURL("**/projects/test-proj-123");
    await expect(page).toHaveURL(/\/projects\/test-proj-123/);
  });

  test("shows submitting state on form", async ({ page }) => {
    // Delay API response to capture submitting state
    await page.route("**/api/v1/projects", async (route) => {
      await new Promise((r) => setTimeout(r, 500));
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ project_id: "p-1", ws_url: "/ws/p-1", status: "pending" }),
      });
    });

    await page.getByRole("button", { name: /new project/i }).first().click();
    await page
      .getByPlaceholder("Describe the application you want to build...")
      .fill("Build something");
    await page.getByRole("button", { name: /create project/i }).click();

    await expect(page.getByRole("button", { name: /creating/i })).toBeVisible();
  });
});

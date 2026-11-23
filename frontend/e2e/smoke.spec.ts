import { expect, test } from "./fixtures";
import { THEME_KEY } from "./pages";

test.describe("smoke", () => {
  test("the app opens, with the permission warning, and no console errors", async ({ page }) => {
    const problems: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") problems.push(message.text());
    });
    page.on("pageerror", (error) => problems.push(error.message));

    await page.goto("/");
    await expect(page).toHaveTitle("Blindspot");
    await expect(page.getByText("Find what you cannot see")).toBeVisible();
    await expect(
      page.getByText(/only run it against systems you own or have written permission/i),
    ).toBeVisible();
    expect(problems).toEqual([]);
  });

  test("the API answers through the same address as the page", async ({ request }) => {
    const response = await request.get("/api/health");
    expect(response.status()).toBe(200);
    const body = (await response.json()) as { status: string };
    expect(body.status).toBe("ok");
  });

  test("an unknown API path is a problem document, not a stack trace", async ({ request }) => {
    const response = await request.get("/api/does-not-exist");
    expect(response.status()).toBe(404);
    expect(response.headers()["content-type"]).toContain("application/problem+json");
    expect(await response.text()).not.toContain("Traceback");
  });

  test("the theme button switches the theme, and the choice survives a reload", async ({
    page,
  }) => {
    await page.addInitScript((key) => {
      if (sessionStorage.getItem("seeded") === null) {
        localStorage.setItem(key, "midnight");
        sessionStorage.setItem("seeded", "1");
      }
    }, THEME_KEY);
    await page.goto("/");

    const app = page.locator(".v-application");
    await expect(app).toHaveClass(/v-theme--midnight/);
    await page.getByRole("button", { name: "Switch to the light theme" }).click();
    await expect(app).toHaveClass(/v-theme--daylight/);
    await expect(page.getByRole("button", { name: "Switch to the dark theme" })).toBeVisible();

    await page.reload();
    await expect(app).toHaveClass(/v-theme--daylight/);
    expect(await page.evaluate((key) => localStorage.getItem(key), THEME_KEY)).toBe("daylight");
  });

  test("the menu shrinks to icons on a large screen and is a drawer on a phone", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    const menu = page.getByRole("navigation", { name: "Main" });
    await expect(menu.getByText("Overview")).toBeInViewport();
    await page.getByRole("button", { name: "Collapse the menu" }).click();
    await expect(page.locator(".v-navigation-drawer")).toHaveClass(/v-navigation-drawer--rail/);
    await page.reload();
    await expect(page.locator(".v-navigation-drawer")).toHaveClass(/v-navigation-drawer--rail/);

    await page.setViewportSize({ width: 390, height: 800 });
    await expect(page.getByRole("button", { name: "Open the menu" })).toBeVisible();
    await expect(page.locator(".v-navigation-drawer")).not.toBeInViewport();
    await page.getByRole("button", { name: "Open the menu" }).click();
    await expect(page.locator(".v-navigation-drawer")).toBeInViewport();
    await menu.getByRole("link", { name: "Overview" }).click();
    await expect(page.locator(".v-navigation-drawer")).not.toBeInViewport();
  });

  test("the command palette opens with Ctrl+K, finds an action and runs it", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goto("/");
    await expect(page.locator(".v-application")).toHaveClass(/v-theme--midnight/);
    await page.keyboard.press("Control+k");
    const search = page.getByRole("textbox", { name: "Search pages and actions" });
    await expect(search).toBeFocused();
    await search.fill("light");
    await page.keyboard.press("Enter");
    await expect(page.locator(".v-application")).toHaveClass(/v-theme--daylight/);
    await expect(search).toBeHidden();
  });

  test("an unknown address says so and the title follows the page", async ({ page }) => {
    await page.goto("/no-such-page");
    await expect(page.getByRole("heading", { name: "Page not found", level: 1 })).toBeVisible();
    await expect(page).toHaveTitle("Page not found · Blindspot");
    await page.getByRole("button", { name: "Back to the overview" }).click();
    await expect(page).toHaveTitle("Blindspot");
  });

  test("the visual effects can be turned off, and stay off after a reload", async ({ page }) => {
    await page.goto("/");
    const app = page.locator(".v-application");
    await expect(app).toHaveClass(/bs-effects/);
    await page.getByRole("button", { name: "Turn visual effects off" }).click();
    await expect(app).not.toHaveClass(/bs-effects/);
    await page.reload();
    await expect(app).not.toHaveClass(/bs-effects/);
  });

  test("the first visit follows the system's colour scheme", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/");
    await expect(page.locator(".v-application")).toHaveClass(/v-theme--daylight/);
  });
});

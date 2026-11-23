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

  test("the first visit follows the system's colour scheme", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/");
    await expect(page.locator(".v-application")).toHaveClass(/v-theme--daylight/);
  });
});

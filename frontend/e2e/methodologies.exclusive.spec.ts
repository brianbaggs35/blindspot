import { expect, test } from "./fixtures";

const WSTG = "OWASP Web Security Testing Guide";

// Turning a methodology off takes it out of the list every new pentest offers, for the whole
// installation. The playwright config runs this file after everything else, on its own, so no
// other spec is creating a pentest while the methodology is off.
test.describe("Methodologies (exclusive)", () => {
  test.describe.configure({ mode: "serial" });

  test("turns the methodology off and on again", async ({ page }) => {
    await page.goto("/methodologies");
    const toggle = page.getByLabel("Offer this methodology for new pentests");
    await expect(toggle).toBeChecked();
    await page.getByText("Offer this methodology for new pentests").click();
    await expect(page.getByText(`${WSTG} is off.`)).toBeVisible();
    await expect(toggle).not.toBeChecked();
    await page.getByText("Offer this methodology for new pentests").click();
    await expect(page.getByText(`${WSTG} is on.`)).toBeVisible();
    await expect(toggle).toBeChecked();
  });
});

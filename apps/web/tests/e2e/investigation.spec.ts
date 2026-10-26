import { expect, test } from "@playwright/test";

/**
 * Definition-of-Done end-to-end flow, run against a live docker-compose stack:
 *   register → create case (acknowledgment gate) → add a seed + run collectors →
 *   see a collector-produced node (via the Entities table) → export a report.
 *
 * "See a node": Cytoscape renders to <canvas>, which isn't DOM-queryable, so we verify
 * the same data through the Entities table. example.com's NS records resolve to the stable
 * *.iana-servers.net hosts, giving a deterministic "dns_records produced a node" assertion.
 */
const EMAIL = `e2e-${Date.now()}@lighthouse-osint.io`;
const PASSWORD = "Sup3rSecret!2024";

test("full investigation flow", async ({ page }) => {
  // ---- Register (auto-logs in) ----
  await page.goto("/register");
  await page.locator('input[type="email"]').fill(EMAIL);
  await page.locator('input[type="password"]').first().fill(PASSWORD);
  await page.locator('input[type="password"]').nth(1).fill(PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL("**/dashboard", { timeout: 30_000 });

  // ---- Create a case through the acknowledgment gate ----
  await page.goto("/cases");
  await page.getByRole("button", { name: /new case/i }).first().click();
  await page.locator("#case-name").fill("E2E Recon");
  await page.locator("#case-legal-basis").fill("Authorized end-to-end automated test engagement #E2E-001.");
  // The "Create case" button stays disabled until the AUP checkbox is ticked — verify the gate.
  const createBtn = page.getByRole("button", { name: /^create case$/i });
  await expect(createBtn).toBeDisabled();
  await page.getByRole("checkbox").click();
  await expect(createBtn).toBeEnabled();
  await createBtn.click();
  await page.waitForURL(/\/cases\/.*\/graph/, { timeout: 30_000 });

  // ---- Add a seed domain and run collectors ----
  await page.getByRole("button", { name: /add seed/i }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  // Ensure the type is Domain.
  await dialog.getByRole("combobox").first().click();
  await page.getByRole("option", { name: /^domain$/i }).click();
  await page.locator("#seed-value").fill("example.com");
  await dialog.getByRole("button", { name: /add seed/i }).click();
  await expect(dialog).toBeHidden({ timeout: 15_000 });

  // ---- Entities tab: the seed is present immediately ----
  await page.getByRole("link", { name: /entities/i }).first().click();
  await page.waitForURL("**/entities", { timeout: 15_000 });
  await expect(page.getByText("example.com").first()).toBeVisible({ timeout: 30_000 });

  // ---- Collector-produced nodes appear ----
  // Running collectors on the domain yields several new entities (IPs, NS subdomains, a URL).
  // We assert on the table's total-count footer ("X–Y of N") rather than a specific row,
  // because (a) the row values depend on example.com's live DNS and (b) low-confidence rows
  // can be virtualized out of the DOM. The count comes straight from the API, so it's stable.
  await expect
    .poll(
      async () => {
        await page.reload();
        const text =
          (await page
            .getByText(/\d+\s*[–-]\s*\d+\s+of\s+\d+/)
            .first()
            .textContent()
            .catch(() => "")) || "";
        const m = text.match(/of\s+(\d+)/);
        return m ? parseInt(m[1], 10) : 0;
      },
      { timeout: 90_000, intervals: [4000] },
    )
    .toBeGreaterThan(1);

  // ---- Visit the graph so a snapshot is captured for the report ----
  await page.getByRole("link", { name: /^graph$/i }).first().click();
  await page.waitForURL("**/graph", { timeout: 15_000 });
  await page.waitForTimeout(4000); // let fcose settle + layoutstop capture the PNG

  // ---- Export a cited PDF report (default format; includes graph snapshot + provenance) ----
  await page.getByRole("link", { name: /^report$/i }).first().click();
  await page.waitForURL("**/report", { timeout: 15_000 });
  await page.getByRole("button", { name: /generate report/i }).click();
  // A downloadable PDF artifact link appears once server-side generation completes.
  await expect(page.locator('a[href*="format=pdf"]').first()).toBeVisible({ timeout: 45_000 });
});

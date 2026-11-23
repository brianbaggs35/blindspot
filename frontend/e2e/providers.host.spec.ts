import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { expect, test } from "./fixtures";
import { card, newProvider } from "./providers";
import { pickOption } from "./vuetify";

// A pretend Ollama on this machine, so the test and fetch buttons have something to talk to. The
// container cannot reach a server in the test process, so these run in host mode only
// (playwright.config.ts leaves `*.host.spec.ts` out of the container run).
const MODELS = ["llama3.3:70b", "nomic-embed-text", "qwen3:8b"];
const SHOWN: Record<string, object> = {
  "llama3.3:70b": {
    capabilities: ["completion", "tools"],
    model_info: { "llama.context_length": 131072 },
  },
  "nomic-embed-text": { capabilities: ["embedding"], model_info: {} },
  "qwen3:8b": { capabilities: ["completion", "tools", "thinking"], model_info: {} },
};

let server: Server;
let address = "";

test.beforeAll(async () => {
  server = createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk: Buffer) => chunks.push(chunk));
    request.on("end", () => {
      response.setHeader("Content-Type", "application/json");
      if (request.url === "/api/tags") {
        response.end(JSON.stringify({ models: MODELS.map((name) => ({ name })) }));
        return;
      }
      const asked = JSON.parse(Buffer.concat(chunks).toString() || "{}") as { model?: string };
      response.end(JSON.stringify(SHOWN[asked.model ?? ""] ?? {}));
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  address = `http://127.0.0.1:${String((server.address() as AddressInfo).port)}`;
});

test.afterAll(() => {
  server.close();
});

test("tests the connection, fetches the models and adds the ones picked", async ({
  page,
  playwright,
  baseURL,
}) => {
  const made = await newProvider(playwright, baseURL, address);
  await page.goto("/ai-providers");
  const mine = card(page, made.name);
  await mine.getByRole("button", { name: "Test" }).click();
  await expect(mine.locator(".v-alert")).toContainText("Connected. 2 models are available.");

  await mine.getByRole("button", { name: "Models" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Fetch models" }).click();
  await expect(dialog).toContainText("The provider offers 2 models");
  await expect(dialog).not.toContainText("nomic-embed-text");
  const offered = dialog.getByRole("region", { name: "Models the provider offers" });
  await offered.getByRole("checkbox", { name: /llama3\.3:70b/ }).check();
  await dialog.getByRole("button", { name: "Add 1 selected" }).click();
  const row = dialog.locator(".v-list-item", { hasText: "llama3.3:70b" });
  await expect(row).toContainText("131,072 tokens");
  await expect(row).toContainText("free");
  await dialog.getByRole("button", { name: "Fetch models" }).click();
  await expect(dialog).toContainText("The provider offers 2 models");
  await expect(offered.getByRole("checkbox", { name: /qwen3:8b/ })).toBeVisible();
  await expect(offered.getByRole("checkbox", { name: /llama3\.3:70b/ })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Close" }).click();

  await pickOption(page, page, "Test agents: run one test each", `${made.name} · llama3.3:70b`);
  await expect(page.getByText("Saved the default for test agents.")).toBeVisible();
});

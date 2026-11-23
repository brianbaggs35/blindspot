import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { createMemoryHistory } from "vue-router";
import { buildCommands, filterCommands, type Command } from "../src/commands";
import { admin } from "./helpers";
import { createBlindspotRouter } from "../src/router";
import { useAuthStore } from "../src/stores/auth";
import { useThemeStore } from "../src/stores/theme";
import { useUiStore } from "../src/stores/ui";

function command(title: string, hint: string): Command {
  return { id: title, title, hint, icon: "", run: () => undefined };
}

describe("commands", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    useAuthStore().$patch({ loaded: true, user: admin });
  });

  it("offers every page in the menu and the appearance actions", () => {
    const commands = buildCommands(createBlindspotRouter(createMemoryHistory()));
    expect(commands.map((entry) => entry.id)).toEqual([
      "go:/",
      "go:/pentests",
      "go:/methodologies",
      "go:/ai-providers",
      "go:/users",
      "go:/audit",
      "go:/account",
      "theme",
      "effects",
    ]);
    expect(commands.map((entry) => entry.title)).toEqual([
      "Overview",
      "Pentests",
      "Methodologies",
      "AI providers",
      "Users",
      "Audit log",
      "Account",
      "Switch to the light theme",
      "Turn visual effects off",
    ]);
  });

  it("runs the actions and words them for what happens next", async () => {
    const router = createBlindspotRouter(createMemoryHistory());
    const first = buildCommands(router);
    await first[0]?.run();
    expect(router.currentRoute.value.path).toBe("/");
    first[7]?.run();
    first[8]?.run();
    expect(useThemeStore().name).toBe("daylight");
    expect(useUiStore().effects).toBe(false);
    const second = buildCommands(router);
    expect(second.map((entry) => entry.title).slice(7)).toEqual([
      "Switch to the dark theme",
      "Turn visual effects on",
    ]);
  });

  it("filters by every word, in any case, in the title or the hint", () => {
    const all = [command("Overview", "Go to"), command("Findings", "Go to")];
    expect(filterCommands(all, "")).toEqual(all);
    expect(filterCommands(all, "  GO  find")).toEqual([all[1]]);
    expect(filterCommands(all, "zzz")).toEqual([]);
  });
});

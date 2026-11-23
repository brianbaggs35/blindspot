import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { createMemoryHistory } from "vue-router";
import { buildCommands, filterCommands, type Command } from "../src/commands";
import { createBlindspotRouter } from "../src/router";
import { useThemeStore } from "../src/stores/theme";
import { useUiStore } from "../src/stores/ui";

function command(title: string, hint: string): Command {
  return { id: title, title, hint, icon: "", run: () => undefined };
}

describe("commands", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("offers every page in the menu and the appearance actions", () => {
    const commands = buildCommands(createBlindspotRouter(createMemoryHistory()));
    expect(commands.map((entry) => entry.id)).toEqual(["go:/", "theme", "effects"]);
    expect(commands.map((entry) => entry.title)).toEqual([
      "Overview",
      "Switch to the light theme",
      "Turn visual effects off",
    ]);
  });

  it("runs the actions and words them for what happens next", async () => {
    const router = createBlindspotRouter(createMemoryHistory());
    const first = buildCommands(router);
    await first[0]?.run();
    expect(router.currentRoute.value.path).toBe("/");
    first[1]?.run();
    first[2]?.run();
    expect(useThemeStore().name).toBe("daylight");
    expect(useUiStore().effects).toBe(false);
    const second = buildCommands(router);
    expect(second.map((entry) => entry.title).slice(1)).toEqual([
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

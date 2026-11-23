import type { Router } from "vue-router";
import { mdiMotionPauseOutline, mdiMotionPlayOutline, mdiThemeLightDark } from "@mdi/js";
import { navSections } from "./navigation";
import { useAuthStore } from "./stores/auth";
import { useThemeStore } from "./stores/theme";
import { useUiStore } from "./stores/ui";

// Everything the command palette (Ctrl+K or ⌘K) can do.
export interface Command {
  id: string;
  title: string;
  hint: string;
  icon: string;
  run: () => unknown;
}

export function buildCommands(router: Router): Command[] {
  const theme = useThemeStore();
  const ui = useUiStore();
  const pages = navSections(router, useAuthStore().isAdmin).flatMap((section) =>
    section.items.map((item): Command => ({
      id: `go:${item.to}`,
      title: item.label,
      hint: "Go to",
      icon: item.icon,
      run: () => router.push(item.to),
    })),
  );
  return [
    ...pages,
    {
      id: "theme",
      title: theme.isDark ? "Switch to the light theme" : "Switch to the dark theme",
      hint: "Appearance",
      icon: mdiThemeLightDark,
      run: () => {
        theme.toggle();
      },
    },
    {
      id: "effects",
      title: ui.effects ? "Turn visual effects off" : "Turn visual effects on",
      hint: "Appearance",
      icon: ui.effects ? mdiMotionPauseOutline : mdiMotionPlayOutline,
      run: () => {
        ui.toggleEffects();
      },
    },
  ];
}

// Every word typed has to be in the title or the hint, in any case.
export function filterCommands(commands: readonly Command[], query: string): Command[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return commands.filter((command) => {
    const text = `${command.title} ${command.hint}`.toLowerCase();
    return words.every((word) => text.includes(word));
  });
}

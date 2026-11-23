import { createMemoryHistory, createRouter } from "vue-router";
import { describe, expect, it } from "vitest";
import { navSections, pageTitle } from "../src/navigation";

const component = { render: () => null };

describe("navigation", () => {
  it("lists the pages that ask to be in the menu, by group and order", () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: "/b",
          component,
          meta: { nav: { label: "B", group: "work", order: 20, icon: "b" } },
        },
        {
          path: "/a",
          component,
          meta: { nav: { label: "A", group: "work", order: 10, icon: "a" } },
        },
        {
          path: "/users",
          component,
          meta: { nav: { label: "Users", group: "system", order: 10, icon: "u" } },
        },
        { path: "/hidden", component },
      ],
    });
    expect(navSections(router)).toEqual([
      {
        id: "work",
        title: "Work",
        items: [
          { label: "A", to: "/a", icon: "a" },
          { label: "B", to: "/b", icon: "b" },
        ],
      },
      { id: "system", title: "System", items: [{ label: "Users", to: "/users", icon: "u" }] },
    ]);
  });

  it("leaves out a group with no pages", () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    expect(navSections(router)).toEqual([]);
  });

  it("names the tab after the page, or just the app", () => {
    expect(pageTitle(undefined)).toBe("Blindspot");
    expect(pageTitle("Findings")).toBe("Findings · Blindspot");
  });
});

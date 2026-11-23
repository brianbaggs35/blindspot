import type { Router } from "vue-router";

// A page appears in the menu by giving its route `meta.nav`; nothing else lists pages.
export const NAV_GROUPS = [
  { id: "work", title: "Work" },
  { id: "system", title: "System" },
] as const;

export type NavGroupId = (typeof NAV_GROUPS)[number]["id"];

export interface NavSettings {
  /** The words in the menu. */
  label: string;
  group: NavGroupId;
  order: number;
  /** An @mdi/js icon path. */
  icon: string;
}

export interface NavItem {
  label: string;
  to: string;
  icon: string;
}

export interface NavSection {
  id: NavGroupId;
  title: string;
  items: NavItem[];
}

declare module "vue-router" {
  interface RouteMeta {
    /** The page's name in the browser tab. */
    title?: string;
    /** Present when the page belongs in the menu. */
    nav?: NavSettings;
  }
}

export function navSections(router: Router): NavSection[] {
  const listed = router.getRoutes().flatMap((route) => {
    const { nav } = route.meta;
    return nav ? [{ nav, to: route.path }] : [];
  });
  return NAV_GROUPS.map(({ id, title }) => ({
    id,
    title,
    items: listed
      .filter(({ nav }) => nav.group === id)
      .sort((a, b) => a.nav.order - b.nav.order)
      .map(({ nav, to }) => ({ label: nav.label, to, icon: nav.icon })),
  })).filter((section) => section.items.length > 0);
}

export function pageTitle(title: string | undefined): string {
  return title ? `${title} · Blindspot` : "Blindspot";
}

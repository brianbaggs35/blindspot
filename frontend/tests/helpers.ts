import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { vi } from "vitest";
import type { Component } from "vue";
import { createMemoryHistory } from "vue-router";
import type { User } from "../src/api/types";
import { createBlindspotVuetify } from "../src/plugins/vuetify";
import { createBlindspotRouter } from "../src/router";
import { useAuthStore } from "../src/stores/auth";

export const admin: User = {
  id: "00000000-0000-7000-8000-000000000001",
  username: "ada",
  display_name: "Ada Admin",
  role: "admin",
  is_active: true,
  last_sign_in_at: "2026-11-20T10:00:00Z",
  created_at: "2026-11-01T10:00:00Z",
  terms_accepted: true,
};

export const viewer: User = {
  ...admin,
  id: "00000000-0000-7000-8000-000000000002",
  username: "vic",
  display_name: "Vic Viewer",
  role: "viewer",
};

interface Options {
  /** Who is signed in; null for a visitor. Defaults to the administrator. */
  user?: User | null;
  setupRequired?: boolean;
}

// Mounts a component with everything the app provides: the stores, the router and Vuetify.
export async function mountWithApp(
  component: Component,
  path = "/",
  props: object = {},
  { user = admin, setupRequired = false }: Options = {},
) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.$patch({ loaded: true, user, setupRequired });
  const router = createBlindspotRouter(createMemoryHistory());
  const vuetify = createBlindspotVuetify();
  await router.push(path);
  await router.isReady();
  const wrapper = mount(component, {
    props,
    attachTo: document.body,
    global: { plugins: [pinia, router, vuetify] },
  });
  return { wrapper, router, vuetify, auth };
}

export function setWidth(width: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  window.dispatchEvent(new Event("resize"));
}

export interface Reply {
  status?: number;
  json?: unknown;
  headers?: Record<string, string>;
}

export type Handler = Reply | ((body: unknown, call: { method: string; path: string }) => Reply);

// Replaces fetch with answers for "METHOD /path" keys. An unknown request is a failure, so a test
// never silently talks to a server that is not there.
export function mockApi(handlers: Record<string, Handler>) {
  const table = new Map(Object.entries(handlers));
  const calls: { key: string; body: unknown }[] = [];
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = input as string;
    const key = `${method} ${path}`;
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
    calls.push({ key, body });
    const handler = table.get(key);
    if (handler === undefined) return Promise.reject(new Error(`no mock for ${key}`));
    const reply = typeof handler === "function" ? handler(body, { method, path }) : handler;
    const status = reply.status ?? (reply.json === undefined ? 204 : 200);
    return Promise.resolve(
      new Response(status === 204 ? null : JSON.stringify(reply.json ?? {}), {
        status,
        headers: { "Content-Type": "application/json", ...reply.headers },
      }),
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

// Dialogs and menus are teleported to the body, outside the wrapper, so they are found there.
/** What a screen reader calls the open dialog: the name on the dialog itself. */
export function dialogName() {
  return Array.from(document.body.querySelectorAll(".v-overlay--active[aria-label]"))
    .at(-1)
    ?.getAttribute("aria-label");
}

export function dialogButton(label: string) {
  // The newest dialog is last in the page; one that was closed may still be there.
  return Array.from(document.body.querySelectorAll<HTMLButtonElement>(".v-dialog button")).findLast(
    (button) => button.textContent.trim() === label,
  );
}

export async function fillDialog(values: Record<string, string>) {
  for (const [selector, value] of Object.entries(values)) {
    const input = document.body.querySelector<HTMLInputElement>(`.v-dialog ${selector}`);
    if (input === null) throw new Error(`no ${selector} in the dialog`);
    input.value = value;
    input.dispatchEvent(new Event("input"));
  }
  await flushPromises();
}

export async function submitDialog() {
  document.body
    .querySelector<HTMLFormElement>(".v-dialog form")
    ?.dispatchEvent(new Event("submit", { cancelable: true }));
  await flushPromises();
}

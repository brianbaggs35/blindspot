import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import type { Component } from "vue";
import { createMemoryHistory } from "vue-router";
import { createBlindspotVuetify } from "../src/plugins/vuetify";
import { createBlindspotRouter } from "../src/router";

// Mounts a component with everything the app provides: the store, router and Vuetify.
export async function mountWithApp(component: Component, path = "/", props: object = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createBlindspotRouter(createMemoryHistory());
  const vuetify = createBlindspotVuetify();
  await router.push(path);
  await router.isReady();
  const wrapper = mount(component, {
    props,
    attachTo: document.body,
    global: { plugins: [pinia, router, vuetify] },
  });
  return { wrapper, router, vuetify };
}

export function setWidth(width: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  window.dispatchEvent(new Event("resize"));
}

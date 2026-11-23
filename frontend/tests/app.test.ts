import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";
import { VNavigationDrawer } from "vuetify/components";
import App from "../src/App.vue";
import { useThemeStore } from "../src/stores/theme";
import { useUiStore } from "../src/stores/ui";
import HomeView from "../src/views/HomeView.vue";
import { mountWithApp, setWidth } from "./helpers";

describe("App", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    setWidth(1280);
  });
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("shows the name, the menu and the home page", async () => {
    const { wrapper } = await mountWithApp(App);
    await flushPromises();
    expect(wrapper.text()).toContain("Blindspot");
    expect(wrapper.text()).toContain("Find what you cannot see");
    expect(wrapper.get("nav[aria-label='Main']").text()).toContain("Overview");
  });

  it("switches the theme from the app bar and says what the button does", async () => {
    const { wrapper, vuetify } = await mountWithApp(App);
    const button = wrapper.get("button[aria-label='Switch to the light theme']");
    await button.trigger("click");
    expect(useThemeStore().name).toBe("daylight");
    expect(vuetify.theme.name.value).toBe("daylight");
    expect(wrapper.find("button[aria-label='Switch to the dark theme']").exists()).toBe(true);
  });

  it("turns the visual effects off and on, and says which", async () => {
    const { wrapper } = await mountWithApp(App);
    const app = wrapper.get(".v-application");
    expect(app.classes()).toContain("bs-effects");
    await wrapper.get("button[aria-label='Turn visual effects off']").trigger("click");
    expect(app.classes()).not.toContain("bs-effects");
    await wrapper.get("button[aria-label='Turn visual effects on']").trigger("click");
    expect(app.classes()).toContain("bs-effects");
  });

  it("collapses the menu to icons on a large screen, and remembers it", async () => {
    const { wrapper } = await mountWithApp(App);
    const toggle = wrapper.get("button[aria-label='Collapse the menu']");
    expect(toggle.attributes("aria-expanded")).toBe("true");
    await toggle.trigger("click");
    expect(useUiStore().navCollapsed).toBe(true);
    expect(localStorage.getItem("blindspot.nav")).toBe("collapsed");
    expect(wrapper.get(".v-navigation-drawer").classes()).toContain("v-navigation-drawer--rail");
    await wrapper.get("button[aria-label='Expand the menu']").trigger("click");
    expect(useUiStore().navCollapsed).toBe(false);
  });

  it("opens the menu as a drawer on a phone, and closes it after going to a page", async () => {
    setWidth(390);
    const { wrapper, router } = await mountWithApp(App);
    await nextTick();
    await wrapper.get("button[aria-label='Search pages and actions']").trigger("click");
    expect(useUiStore().paletteOpen).toBe(true);
    const toggle = wrapper.get("button[aria-label='Open the menu']");
    expect(toggle.attributes("aria-expanded")).toBe("false");
    await toggle.trigger("click");
    expect(wrapper.get("button[aria-label='Close the menu']").attributes("aria-expanded")).toBe(
      "true",
    );
    wrapper.getComponent(VNavigationDrawer).vm.$emit("update:modelValue", false);
    await nextTick();
    expect(wrapper.find("button[aria-label='Open the menu']").exists()).toBe(true);
    await wrapper.get("button[aria-label='Open the menu']").trigger("click");
    await wrapper.get("nav[aria-label='Main'] a").trigger("click");
    expect(wrapper.find("button[aria-label='Open the menu']").exists()).toBe(true);
    await wrapper.get("button[aria-label='Open the menu']").trigger("click");
    await router.push("/nowhere");
    await flushPromises();
    expect(wrapper.find("button[aria-label='Open the menu']").exists()).toBe(true);
    await wrapper.get("button[aria-label='Open the menu']").trigger("click");
    await wrapper.get("button[aria-label='Close the menu']").trigger("click");
    expect(wrapper.find("button[aria-label='Open the menu']").exists()).toBe(true);
  });

  it("opens the command palette from the button and from Ctrl+K, and closes it again", async () => {
    const { wrapper } = await mountWithApp(App);
    const ui = useUiStore();
    const search = wrapper.findAll("button").find((button) => button.text().startsWith("Search"));
    await search?.trigger("click");
    expect(ui.paletteOpen).toBe(true);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }));
    expect(ui.paletteOpen).toBe(false);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "K", metaKey: true }));
    expect(ui.paletteOpen).toBe(true);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k" }));
    expect(ui.paletteOpen).toBe(true);
  });

  it("stops listening for the shortcut when it goes away", async () => {
    const { wrapper } = await mountWithApp(App);
    const ui = useUiStore();
    wrapper.unmount();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }));
    expect(ui.paletteOpen).toBe(false);
  });

  it("moves focus to the content from the skip link", async () => {
    const { wrapper } = await mountWithApp(App);
    await wrapper.get("a.bs-skip").trigger("click");
    expect(document.activeElement?.id).toBe("content");
  });

  it("skip link does nothing harmful when the content is missing", async () => {
    const { wrapper } = await mountWithApp(App);
    document.getElementById("content")?.removeAttribute("id");
    await wrapper.get("a.bs-skip").trigger("click");
    expect(document.activeElement).toBe(document.body);
  });
});

describe("HomeView", () => {
  it("carries the permission reminder", async () => {
    const { wrapper } = await mountWithApp(HomeView);
    expect(wrapper.text()).toContain("written permission");
    expect(wrapper.get("h1").text()).toBe("Overview");
  });
});

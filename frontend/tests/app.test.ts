import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { createMemoryHistory } from "vue-router";
import { nextTick } from "vue";
import App from "../src/App.vue";
import HomeView from "../src/views/HomeView.vue";
import { createBlindspotVuetify } from "../src/plugins/vuetify";
import { createBlindspotRouter } from "../src/router";
import { useThemeStore } from "../src/stores/theme";

async function mountApp() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createBlindspotRouter(createMemoryHistory());
  const vuetify = createBlindspotVuetify();
  await router.push("/");
  await router.isReady();
  const wrapper = mount(App, { global: { plugins: [pinia, router, vuetify] } });
  return { wrapper, vuetify };
}

describe("App", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("shows the name and the home page", async () => {
    const { wrapper } = await mountApp();
    await nextTick();
    expect(wrapper.text()).toContain("Blindspot");
    expect(wrapper.text()).toContain("Find what you cannot see");
  });

  it("switches the theme from the app bar and says what the button does", async () => {
    const { wrapper, vuetify } = await mountApp();
    const button = wrapper.get("button[aria-label]");
    expect(button.attributes("aria-label")).toBe("Switch to the light theme");
    await button.trigger("click");
    expect(useThemeStore().name).toBe("daylight");
    expect(vuetify.theme.name.value).toBe("daylight");
    expect(wrapper.get("button[aria-label]").attributes("aria-label")).toBe(
      "Switch to the dark theme",
    );
  });
});

describe("HomeView", () => {
  it("carries the permission reminder", () => {
    const wrapper = mount(HomeView, { global: { plugins: [createBlindspotVuetify()] } });
    expect(wrapper.text()).toContain("written permission");
  });
});

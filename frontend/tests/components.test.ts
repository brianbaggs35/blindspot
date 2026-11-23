import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory } from "vue-router";
import { describe, expect, it } from "vitest";
import { VDialog } from "vuetify/components";
import { createBlindspotVuetify } from "../src/plugins/vuetify";
import { createBlindspotRouter } from "../src/router";
import AuthCard from "../src/components/AuthCard.vue";
import FormDialog from "../src/components/FormDialog.vue";
import PasswordField from "../src/components/PasswordField.vue";
import PasswordRules from "../src/components/PasswordRules.vue";
import CommandPalette from "../src/components/CommandPalette.vue";
import NavMenu from "../src/components/NavMenu.vue";
import PageHeader from "../src/components/PageHeader.vue";
import StateView from "../src/components/StateView.vue";
import { useThemeStore } from "../src/stores/theme";
import { useUiStore } from "../src/stores/ui";
import NotFoundView from "../src/views/NotFoundView.vue";
import { mountWithApp } from "./helpers";

describe("NavMenu", () => {
  it("shows group headings and labels when expanded", async () => {
    const { wrapper } = await mountWithApp(NavMenu, "/", { rail: false });
    expect(wrapper.text()).toContain("Work");
    expect(wrapper.text()).toContain("Overview");
    expect(wrapper.find(".v-tooltip").exists()).toBe(false);
  });

  it("drops the headings, keeping a divider between groups, when it is only icons", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const router = createBlindspotRouter(createMemoryHistory());
    router.addRoute({
      path: "/users",
      component: { render: () => null },
      meta: { nav: { label: "Users", group: "system", order: 1, icon: "u" } },
    });
    await router.push("/");
    const wrapper = mount(NavMenu, {
      props: { rail: true },
      global: { plugins: [pinia, router, createBlindspotVuetify()] },
    });
    expect(wrapper.find(".v-divider").exists()).toBe(true);
    expect(wrapper.text()).not.toContain("System");
    expect(wrapper.findAll("a")).toHaveLength(4);
  });

  it("says when a link is used", async () => {
    const { wrapper } = await mountWithApp(NavMenu, "/", { rail: false });
    await wrapper.get("a").trigger("click");
    expect(wrapper.emitted("navigate")).toHaveLength(1);
  });

  it("is only icons with no divider when there is one group", async () => {
    const { wrapper } = await mountWithApp(NavMenu, "/", { rail: true });
    expect(wrapper.text()).not.toContain("Work");
    expect(wrapper.get("a").attributes("href")).toBe("/");
  });
});

describe("PasswordField", () => {
  it("shows and hides the password, saying what the button does", async () => {
    const { wrapper } = await mountWithApp(PasswordField, "/", {
      modelValue: "secret",
      label: "Password",
      purpose: "current",
    });
    expect(wrapper.get("input").attributes("type")).toBe("password");
    await wrapper.get("[aria-label='Show the password']").trigger("click");
    expect(wrapper.get("input").attributes("type")).toBe("text");
    await wrapper.get("[aria-label='Hide the password']").trigger("click");
    expect(wrapper.get("input").attributes("type")).toBe("password");
  });
});

describe("PasswordRules", () => {
  it("says which rules are met, in words as well as colour", async () => {
    const { wrapper } = await mountWithApp(PasswordRules, "/", {
      password: "abc",
      username: "ann",
    });
    expect(wrapper.text()).toContain("At least 12 characters (not yet)");
    expect(wrapper.text()).toContain("At most 256 characters (done)");
  });
});

describe("AuthCard", () => {
  it("shows the logo, the title and the subtitle when given", async () => {
    const { wrapper } = await mountWithApp(AuthCard, "/", { title: "Hello", subtitle: "There" });
    expect(wrapper.get("h1").text()).toBe("Hello");
    expect(wrapper.text()).toContain("There");
    expect(wrapper.find("img").attributes("alt")).toBe("");
    const bare = await mountWithApp(AuthCard, "/", { title: "Hello" });
    expect(bare.wrapper.find("p").exists()).toBe(false);
  });
});

describe("FormDialog", () => {
  const buttons = () =>
    Array.from(document.body.querySelectorAll<HTMLButtonElement>(".v-dialog button"));

  it("shows its fields and the error, and says when it is submitted", async () => {
    const { wrapper } = await mountWithApp(FormDialog, "/", {
      modelValue: true,
      title: "Do it",
      submitLabel: "Go",
      error: "Nope",
    });
    await flushPromises();
    expect(document.body.textContent).toContain("Do it");
    expect(document.body.querySelector("[role=alert]")?.textContent).toContain("Nope");
    document.body.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(wrapper.emitted("submit")).toHaveLength(1);
  });

  it("closes when the dialog itself asks to (a click outside, Escape)", async () => {
    const { wrapper } = await mountWithApp(FormDialog, "/", {
      modelValue: true,
      title: "Do it",
      submitLabel: "Go",
    });
    wrapper.getComponent(VDialog).vm.$emit("update:modelValue", false);
    expect(wrapper.emitted("update:modelValue")).toEqual([[false]]);
  });

  it("closes from Cancel, and cannot be closed from it while it is working", async () => {
    const { wrapper } = await mountWithApp(FormDialog, "/", {
      modelValue: true,
      title: "Do it",
      submitLabel: "Go",
    });
    await flushPromises();
    buttons()
      .find((button) => button.textContent.trim() === "Cancel")
      ?.click();
    await flushPromises();
    expect(wrapper.emitted("update:modelValue")).toEqual([[false]]);
    await wrapper.setProps({ busy: true, danger: true });
    expect(buttons().find((button) => button.textContent.trim() === "Cancel")?.disabled).toBe(true);
  });
});

describe("PageHeader", () => {
  it("shows the title, the subtitle and the actions when given", async () => {
    const { wrapper } = await mountWithApp(PageHeader, "/", { title: "Findings", subtitle: "All" });
    expect(wrapper.get("h1").text()).toBe("Findings");
    expect(wrapper.text()).toContain("All");
    expect(wrapper.find(".bs-page-actions").exists()).toBe(false);
  });

  it("leaves out what it was not given", async () => {
    const { wrapper } = await mountWithApp(PageHeader, "/", { title: "Findings" });
    expect(wrapper.find("p").exists()).toBe(false);
  });
});

describe("StateView", () => {
  it("shows the shape of what is loading, and says so to a screen reader", async () => {
    const { wrapper } = await mountWithApp(StateView, "/", { state: "loading" });
    expect(wrapper.get("output").attributes("aria-label")).toBe("Loading");
    expect(wrapper.find(".v-skeleton-loader").exists()).toBe(true);
  });

  it("shows the content when ready", async () => {
    const { wrapper } = await mountWithApp(StateView, "/", { state: "ready" });
    expect(wrapper.find(".bs-state").exists()).toBe(false);
  });

  it("explains an empty list and offers the next step", async () => {
    const { wrapper } = await mountWithApp(StateView, "/", {
      state: "empty",
      title: "No findings yet",
      message: "Run a pentest to see results.",
      actionLabel: "Start a pentest",
    });
    expect(wrapper.text()).toContain("No findings yet");
    expect(wrapper.text()).toContain("Run a pentest");
    await wrapper.get("button").trigger("click");
    expect(wrapper.emitted("action")).toHaveLength(1);
  });

  it("says what went wrong with an error, without an action when none is given", async () => {
    const { wrapper } = await mountWithApp(StateView, "/", { state: "error", title: "Oops" });
    expect(wrapper.text()).toContain("Oops");
    expect(wrapper.find("button").exists()).toBe(false);
    expect(wrapper.find("p").exists()).toBe(false);
    expect(wrapper.find(".text-error").exists()).toBe(true);
  });
});

describe("NotFoundView", () => {
  it("offers the way back", async () => {
    const { wrapper, router } = await mountWithApp(NotFoundView, "/elsewhere");
    expect(wrapper.get("h1").text()).toBe("Page not found");
    expect(wrapper.text()).toContain("Nothing is at this address");
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/");
  });
});

describe("CommandPalette", () => {
  function items() {
    return Array.from(document.body.querySelectorAll<HTMLElement>(".v-list-item"));
  }

  function search(): HTMLInputElement {
    const input = document.body.querySelector("input");
    if (input === null) throw new Error("the palette has no search box");
    return input;
  }

  async function type(text: string) {
    const input = search();
    input.value = text;
    input.dispatchEvent(new Event("input"));
    await flushPromises();
    return input;
  }

  async function open() {
    const mounted = await mountWithApp(CommandPalette);
    const ui = useUiStore();
    ui.openPalette();
    await flushPromises();
    return { ...mounted, ui };
  }

  it("shows nothing until it is opened, then every command", async () => {
    await mountWithApp(CommandPalette);
    expect(items()).toHaveLength(0);
    useUiStore().openPalette();
    await flushPromises();
    expect(items().map((item) => item.textContent)).toEqual([
      expect.stringContaining("Overview"),
      expect.stringContaining("AI providers"),
      expect.stringContaining("Users"),
      expect.stringContaining("Audit log"),
      expect.stringContaining("Account"),
      expect.stringContaining("Switch to the light theme"),
      expect.stringContaining("Turn visual effects off"),
    ]);
  });

  it("narrows as you type and says when nothing matches", async () => {
    await open();
    await type("theme");
    expect(items()).toHaveLength(1);
    await type("zzz");
    expect(document.body.textContent).toContain("Nothing matches “zzz”.");
  });

  it("runs the first match on Enter and closes", async () => {
    const { ui } = await open();
    const input = await type("theme");
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await flushPromises();
    expect(useThemeStore().name).toBe("daylight");
    expect(ui.paletteOpen).toBe(false);
  });

  it("does nothing on Enter when nothing matches", async () => {
    const { ui } = await open();
    const input = await type("zzz");
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await flushPromises();
    expect(ui.paletteOpen).toBe(true);
  });

  it("runs a command that is clicked, and starts empty the next time", async () => {
    const { ui } = await open();
    items()[6]?.click();
    await flushPromises();
    expect(ui.effects).toBe(false);
    expect(ui.paletteOpen).toBe(false);
    ui.openPalette();
    await flushPromises();
    expect(search().value).toBe("");
  });

  it("closes when the dialog asks to, and puts the cursor in the search box once open", async () => {
    const { wrapper, ui } = await open();
    const dialog = wrapper.getComponent(VDialog);
    dialog.vm.$emit("afterEnter");
    expect(document.activeElement).toBe(search());
    dialog.vm.$emit("update:modelValue", false);
    expect(ui.paletteOpen).toBe(false);
  });
});

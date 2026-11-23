<script setup lang="ts">
import {
  mdiMagnify,
  mdiMenu,
  mdiMotionPauseOutline,
  mdiMotionPlayOutline,
  mdiThemeLightDark,
} from "@mdi/js";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useDisplay, useTheme } from "vuetify";
import CommandPalette from "./components/CommandPalette.vue";
import NavMenu from "./components/NavMenu.vue";
import { useThemeStore } from "./stores/theme";
import { useUiStore } from "./stores/ui";

const themeStore = useThemeStore();
const ui = useUiStore();
const theme = useTheme();
const route = useRoute();
const { mdAndUp } = useDisplay();

watch(
  () => themeStore.name,
  (name) => {
    void theme.change(name);
  },
  { immediate: true },
);

const mobile = computed(() => !mdAndUp.value);
// Phones get a drawer that slides over the page; larger screens get one that stays and can
// shrink to icons.
const drawerOpen = ref(false);
watch(
  () => route.fullPath,
  () => {
    drawerOpen.value = false;
  },
);

function toggleMenu() {
  if (mobile.value) drawerOpen.value = !drawerOpen.value;
  else ui.toggleNav();
}

const menuLabel = computed(() => {
  if (mobile.value) return drawerOpen.value ? "Close the menu" : "Open the menu";
  return ui.navCollapsed ? "Expand the menu" : "Collapse the menu";
});
const themeLabel = computed(() =>
  themeStore.isDark ? "Switch to the light theme" : "Switch to the dark theme",
);
const effectsLabel = computed(() =>
  ui.effects ? "Turn visual effects off" : "Turn visual effects on",
);

function onKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    if (ui.paletteOpen) ui.closePalette();
    else ui.openPalette();
  }
}
onMounted(() => {
  window.addEventListener("keydown", onKeydown);
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKeydown);
});

function skipToContent() {
  document.getElementById("content")?.focus();
}
</script>

<template>
  <v-app :class="{ 'bs-effects': ui.effects }">
    <a class="bs-skip" href="#content" @click.prevent="skipToContent">Skip to the content</a>

    <v-app-bar flat border class="bs-glass">
      <v-btn
        :icon="mdiMenu"
        :aria-label="menuLabel"
        :aria-expanded="mobile ? drawerOpen : !ui.navCollapsed"
        aria-controls="main-menu"
        @click="toggleMenu"
      />
      <router-link to="/" class="bs-brand" aria-label="Blindspot, home">
        <img src="/logo-mark.svg" alt="" width="32" height="32" />
        <span class="bs-wordmark">Blindspot</span>
      </router-link>
      <v-spacer />
      <v-btn
        v-if="!mobile"
        variant="tonal"
        class="mr-2 text-none"
        :prepend-icon="mdiMagnify"
        @click="ui.openPalette()"
      >
        Search
        <kbd class="bs-kbd ml-3" aria-hidden="true">Ctrl K</kbd>
      </v-btn>
      <v-btn
        v-else
        :icon="mdiMagnify"
        aria-label="Search pages and actions"
        @click="ui.openPalette()"
      />
      <v-btn
        :icon="ui.effects ? mdiMotionPauseOutline : mdiMotionPlayOutline"
        :aria-label="effectsLabel"
        @click="ui.toggleEffects()"
      />
      <v-btn :icon="mdiThemeLightDark" :aria-label="themeLabel" @click="themeStore.toggle()" />
    </v-app-bar>

    <v-navigation-drawer
      id="main-menu"
      :model-value="mobile ? drawerOpen : true"
      :permanent="!mobile"
      :temporary="mobile"
      :rail="!mobile && ui.navCollapsed"
      class="bs-glass"
      @update:model-value="drawerOpen = $event"
    >
      <NavMenu :rail="!mobile && ui.navCollapsed" @navigate="drawerOpen = false" />
    </v-navigation-drawer>

    <v-main id="content" tabindex="-1" class="bs-main">
      <router-view />
    </v-main>

    <CommandPalette />
  </v-app>
</template>

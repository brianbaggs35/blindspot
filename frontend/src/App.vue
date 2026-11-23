<script setup lang="ts">
import {
  mdiAccountCircleOutline,
  mdiLogout,
  mdiMagnify,
  mdiMenu,
  mdiMotionPauseOutline,
  mdiMotionPlayOutline,
  mdiThemeLightDark,
} from "@mdi/js";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useDisplay, useTheme } from "vuetify";
import CommandPalette from "./components/CommandPalette.vue";
import NavMenu from "./components/NavMenu.vue";
import { useAuthStore } from "./stores/auth";
import { useThemeStore } from "./stores/theme";
import { useUiStore } from "./stores/ui";

const themeStore = useThemeStore();
const ui = useUiStore();
const theme = useTheme();
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const { mdAndUp } = useDisplay();

watch(
  () => themeStore.name,
  (name) => {
    void theme.change(name);
  },
  { immediate: true },
);

const mobile = computed(() => !mdAndUp.value);
// Setup and sign-in are shown without the menu, and the menu only exists for someone signed in.
const showMenu = computed(() => auth.isSignedIn && route.meta.layout !== "bare");
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

async function signOut() {
  try {
    await auth.signOut();
  } finally {
    await router.push({ name: "sign-in" });
  }
}

function onKeydown(event: KeyboardEvent) {
  if (!showMenu.value) return;
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
        v-if="showMenu"
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
        v-if="showMenu && !mobile"
        variant="tonal"
        class="mr-2 text-none"
        :prepend-icon="mdiMagnify"
        @click="ui.openPalette()"
      >
        Search
        <kbd class="bs-kbd ml-3" aria-hidden="true">Ctrl K</kbd>
      </v-btn>
      <v-btn
        v-else-if="showMenu"
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
      <v-menu v-if="showMenu && auth.user" location="bottom end">
        <template #activator="{ props: activator }">
          <v-btn
            v-bind="activator"
            :icon="mdiAccountCircleOutline"
            :aria-label="`Account menu for ${auth.user.display_name}`"
          />
        </template>
        <v-list min-width="220">
          <v-list-item :title="auth.user.display_name" :subtitle="auth.user.role" />
          <v-divider />
          <v-list-item to="/account" :prepend-icon="mdiAccountCircleOutline" title="Account" />
          <v-list-item :prepend-icon="mdiLogout" title="Sign out" @click="signOut" />
        </v-list>
      </v-menu>
    </v-app-bar>

    <v-navigation-drawer
      v-if="showMenu"
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

    <CommandPalette v-if="showMenu" />
  </v-app>
</template>

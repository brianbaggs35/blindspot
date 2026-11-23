<script setup lang="ts">
import { mdiThemeLightDark } from "@mdi/js";
import { computed, watch } from "vue";
import { useTheme } from "vuetify";
import { useThemeStore } from "./stores/theme";

const store = useThemeStore();
const theme = useTheme();

watch(
  () => store.name,
  (name) => {
    void theme.change(name);
  },
  { immediate: true },
);

const label = computed(() =>
  store.isDark ? "Switch to the light theme" : "Switch to the dark theme",
);
</script>

<template>
  <v-app>
    <v-app-bar flat border>
      <img src="/logo-mark.svg" alt="" width="32" height="32" class="ml-4" />
      <v-app-bar-title class="font-weight-bold">Blindspot</v-app-bar-title>
      <v-spacer />
      <v-btn :icon="mdiThemeLightDark" :aria-label="label" @click="store.toggle()" />
    </v-app-bar>
    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>

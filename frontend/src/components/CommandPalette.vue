<script setup lang="ts">
import { mdiMagnify } from "@mdi/js";
import { computed, ref, useTemplateRef, watch } from "vue";
import { useRouter } from "vue-router";
import { buildCommands, filterCommands, type Command } from "../commands";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const router = useRouter();
const query = ref("");
const field = useTemplateRef<{ focus: () => void }>("field");

const matches = computed(() =>
  // Rebuilt each time the palette opens so the titles ("Switch to the light theme") are current.
  ui.paletteOpen ? filterCommands(buildCommands(router), query.value) : [],
);

watch(
  () => ui.paletteOpen,
  () => {
    query.value = "";
  },
);

async function choose(command: Command) {
  ui.closePalette();
  await command.run();
}

async function chooseFirst() {
  const [first] = matches.value;
  if (first) await choose(first);
}
</script>

<template>
  <v-dialog
    :model-value="ui.paletteOpen"
    max-width="560"
    scrollable
    @update:model-value="ui.closePalette()"
    @after-enter="field?.focus()"
  >
    <v-card aria-label="Command palette" class="bs-palette">
      <v-text-field
        ref="field"
        v-model="query"
        hide-details
        variant="solo-filled"
        flat
        label="Search pages and actions"
        :prepend-inner-icon="mdiMagnify"
        @keydown.enter.prevent="chooseFirst"
      />
      <v-divider />
      <v-card-text class="pa-0">
        <v-list v-if="matches.length > 0" density="comfortable">
          <v-list-item
            v-for="command in matches"
            :key="command.id"
            :prepend-icon="command.icon"
            :title="command.title"
            :subtitle="command.hint"
            @click="choose(command)"
          />
        </v-list>
        <p v-else class="text-body-2 text-medium-emphasis pa-6 text-center">
          Nothing matches “{{ query }}”.
        </p>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

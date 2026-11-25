<script setup lang="ts">
import { computed } from "vue";
import type { Technical } from "../../api/types";
import { sectionsOf } from "../../results";

// The result as the tables of the one result shape, each column sortable.
const props = defineProps<{ technical: Technical }>();
const sections = computed(() => sectionsOf(props.technical));
const warnings = computed(() => (props.technical["warnings"] as string[] | undefined) ?? []);
const cut = computed(() => props.technical["truncated"] === true);
</script>

<template>
  <section aria-label="Technical view">
    <v-alert v-if="cut" type="warning" variant="tonal" class="mb-4">
      The output was long, so only the first part is kept here. The raw view has all of it.
    </v-alert>
    <v-alert v-for="warning in warnings" :key="warning" type="info" variant="tonal" class="mb-4">
      {{ warning }}
    </v-alert>
    <p v-if="sections.length === 0" class="text-body-2">The tool reported nothing of any kind.</p>
    <v-card v-for="section in sections" :key="section.key" border class="mb-4">
      <v-card-item :title="section.title" :subtitle="`${String(section.items.length)} rows`" />
      <v-data-table
        :headers="section.headers"
        :items="section.items"
        :aria-label="section.title"
        density="compact"
        items-per-page="25"
      />
    </v-card>
  </section>
</template>

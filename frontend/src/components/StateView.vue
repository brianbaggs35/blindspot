<script setup lang="ts">
import { mdiAlertCircleOutline, mdiInboxOutline } from "@mdi/js";

// The four states every list or detail view has: loading, empty, failed, and showing its content.
// Loading shows the shape of what is coming instead of a spinner.
defineProps<{
  state: "loading" | "empty" | "error" | "ready";
  title?: string | undefined;
  message?: string | undefined;
  actionLabel?: string | undefined;
}>();

defineEmits<{ action: [] }>();
</script>

<template>
  <output v-if="state === 'loading'" class="bs-state d-block" aria-label="Loading">
    <v-skeleton-loader type="heading, paragraph, paragraph" aria-hidden="true" />
  </output>
  <div v-else-if="state === 'ready'">
    <slot />
  </div>
  <v-sheet v-else class="bs-state text-center pa-8" rounded="lg" border>
    <v-icon
      :icon="state === 'error' ? mdiAlertCircleOutline : mdiInboxOutline"
      :color="state === 'error' ? 'error' : undefined"
      size="48"
      aria-hidden="true"
    />
    <h2 class="text-h6 mt-3">{{ title }}</h2>
    <p v-if="message" class="text-body-2 text-medium-emphasis mt-1">{{ message }}</p>
    <v-btn v-if="actionLabel" class="mt-4" color="primary" variant="tonal" @click="$emit('action')">
      {{ actionLabel }}
    </v-btn>
  </v-sheet>
</template>

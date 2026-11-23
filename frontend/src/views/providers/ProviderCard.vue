<script setup lang="ts">
import {
  mdiKeyOutline,
  mdiLanConnect,
  mdiListBoxOutline,
  mdiPencilOutline,
  mdiTrashCanOutline,
} from "@mdi/js";
import { computed, ref } from "vue";
import { api, describe } from "../../api/client";
import type { ConnectionReport, KindInfo, Provider } from "../../api/types";
import { budgetOf } from "../../providers";

// One provider: where it is, whether it has a key, what it has cost this month, and the things an
// administrator can do with it.
const props = defineProps<{ provider: Provider; kind: KindInfo | undefined; canEdit: boolean }>();
defineEmits<{ models: []; edit: []; remove: [] }>();

const report = ref<ConnectionReport | null>(null);
const testing = ref(false);
const testFailure = ref("");

const budget = computed(() => budgetOf(props.provider));
const keyText = computed(() => {
  const last4 = props.provider.key_last4;
  if (last4 !== null) return `Key ending in ${last4}`;
  return props.kind?.needs_key ? "No key saved" : "No key needed";
});

async function test() {
  testing.value = true;
  testFailure.value = "";
  report.value = null;
  try {
    report.value = await api<ConnectionReport>("POST", `/api/providers/${props.provider.id}/test`);
  } catch (error) {
    testFailure.value = describe(error);
  } finally {
    testing.value = false;
  }
}
</script>

<template>
  <v-card border class="h-100 d-flex flex-column">
    <v-card-item>
      <v-card-title class="d-flex align-center flex-wrap ga-2">
        <span>{{ provider.name }}</span>
        <v-chip size="small" label>{{ kind?.label ?? provider.kind }}</v-chip>
        <v-chip v-if="!provider.enabled" size="small" label color="warning">off</v-chip>
      </v-card-title>
      <v-card-subtitle class="bs-address">{{ provider.base_url }}</v-card-subtitle>
    </v-card-item>
    <v-card-text class="flex-grow-1">
      <p class="d-flex align-center ga-2 text-body-2 mb-2">
        <v-icon :icon="mdiKeyOutline" size="small" aria-hidden="true" />
        {{ keyText }}
      </p>
      <p class="text-body-2 mb-1">{{ budget.text }}</p>
      <v-progress-linear
        v-if="provider.monthly_budget_usd !== null"
        :model-value="budget.percent"
        :color="budget.color"
        height="6"
        rounded
        :aria-label="`Budget used for ${provider.name}`"
        class="mb-3"
      />
      <p class="text-body-2 text-medium-emphasis mb-3">
        {{ provider.model_count }} {{ provider.model_count === 1 ? "model" : "models" }}
      </p>
      <v-alert v-if="testFailure" type="error" variant="tonal" density="compact">
        {{ testFailure }}
      </v-alert>
      <v-alert
        v-else-if="report"
        :type="report.ok ? 'success' : 'error'"
        variant="tonal"
        density="compact"
      >
        {{ report.detail }}
        <span v-if="report.ok">({{ report.latency_ms }} ms)</span>
      </v-alert>
    </v-card-text>
    <v-card-actions class="flex-wrap">
      <v-btn :prepend-icon="mdiListBoxOutline" @click="$emit('models')">Models</v-btn>
      <template v-if="canEdit">
        <v-btn :prepend-icon="mdiLanConnect" :loading="testing" @click="test">Test</v-btn>
        <v-spacer />
        <v-btn
          :icon="mdiPencilOutline"
          variant="text"
          :aria-label="`Edit ${provider.name}`"
          @click="$emit('edit')"
        />
        <v-btn
          :icon="mdiTrashCanOutline"
          variant="text"
          :aria-label="`Delete ${provider.name}`"
          @click="$emit('remove')"
        />
      </template>
    </v-card-actions>
  </v-card>
</template>

<style scoped>
.bs-address {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow-wrap: anywhere;
  white-space: normal;
}
</style>

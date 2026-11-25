<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { BUDGET_FIELDS, RISK_COLORS, RISK_LABELS, budgetProblem } from "../../agents";
import { api, describe } from "../../api/client";
import type { AgentSettings, Budget, Severity } from "../../api/types";

const props = defineProps<{ settings: AgentSettings; canEdit: boolean }>();
const emit = defineEmits<{ saved: [message: string] }>();

const SEVERITIES: Severity[] = ["info", "low", "medium", "high", "critical"];

const draft = ref<Budget>({ ...props.settings.budget });
const busy = ref(false);
const failure = ref("");

watch(
  () => props.settings.budget,
  (next) => {
    draft.value = { ...next };
  },
);

const problem = computed(() => budgetProblem(draft.value));
const changed = computed(
  () => JSON.stringify(draft.value) !== JSON.stringify(props.settings.budget),
);
const isBuiltIn = computed(
  () => JSON.stringify(props.settings.budget) === JSON.stringify(props.settings.built_in_budget),
);

async function save(next: Budget, message: string) {
  busy.value = true;
  failure.value = "";
  try {
    await api<Budget>("PUT", "/api/agents/settings/budget", next);
    emit("saved", message);
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section aria-label="Defaults and presets">
    <v-card border class="mb-6">
      <v-card-item
        title="Caps a mission starts with"
        subtitle="Used when nobody picks others. Code checks every cap before each step."
      />
      <v-form @submit.prevent="save(draft, 'The default caps were saved.')">
        <v-card-text>
          <v-alert v-if="failure" type="error" variant="tonal" class="mb-4" role="alert">
            {{ failure }}
          </v-alert>
          <div class="bs-caps">
            <v-text-field
              v-for="field in BUDGET_FIELDS"
              :key="field.key"
              v-model.number="draft[field.key]"
              :label="field.label"
              :hint="field.hint"
              :min="field.min"
              :max="field.max"
              :step="field.step"
              :readonly="!canEdit"
              type="number"
              persistent-hint
              density="comfortable"
            />
            <v-select
              v-model="draft.verify_from"
              :items="SEVERITIES"
              :readonly="!canEdit"
              label="Replay findings from"
              hint="A finding at or above this is checked again before it counts"
              persistent-hint
              density="comfortable"
            />
          </div>
          <p v-if="problem && canEdit" class="text-body-2 text-error mt-3" role="alert">
            {{ problem }}
          </p>
        </v-card-text>
        <v-card-actions v-if="canEdit">
          <v-spacer />
          <v-btn
            :disabled="busy || isBuiltIn"
            @click="save(settings.built_in_budget, 'The default caps were put back.')"
          >
            Put back the built-in caps
          </v-btn>
          <v-btn
            type="submit"
            color="primary"
            variant="flat"
            :loading="busy"
            :disabled="!changed || problem !== ''"
          >
            Save the caps
          </v-btn>
        </v-card-actions>
      </v-form>
    </v-card>

    <h2 class="text-h6 mb-1">Presets</h2>
    <p class="text-body-2 text-medium-emphasis mb-3">
      A preset sets how far a mission may go and changes some caps. It never goes past the limit of
      the pentest.
    </p>
    <div class="bs-presets">
      <v-card v-for="preset in settings.presets" :key="preset.id" border>
        <v-card-item :title="preset.name" :subtitle="preset.summary" />
        <v-card-text>
          <v-chip :color="RISK_COLORS[preset.max_risk]" size="small" variant="tonal" class="mb-2">
            {{ RISK_LABELS[preset.max_risk] }}
          </v-chip>
          <p class="text-body-2">
            {{ preset.budget.steps_per_test }} steps and
            {{ Math.round(preset.budget.seconds_per_test / 60) }} minutes for a test,
            {{ preset.budget.concurrency }} at a time.
          </p>
        </v-card-text>
      </v-card>
    </div>
  </section>
</template>

<style scoped>
.bs-caps,
.bs-presets {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(min(16rem, 100%), 1fr));
}
</style>

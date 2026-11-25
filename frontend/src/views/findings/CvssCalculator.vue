<script setup lang="ts">
import { ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { CvssScore } from "../../api/types";
import { SEVERITY_COLORS, SEVERITY_LABELS } from "../../results";
import { CVSS_VERSIONS, type CvssVersion, buildVector, parseVector } from "../../findings";

// The base metrics of one CVSS version as selects, the vector they make as text (a vector from
// elsewhere can be pasted), and the score the server works out from it.
const props = defineProps<{ version: CvssVersion }>();
const vector = defineModel<string | null>({ required: true });

const chosen = ref(new Map<string, string>());
const typed = ref("");
const score = ref<CvssScore | null>(null);
const problem = ref("");

function pick(key: string, value: string | null) {
  const next = new Map(chosen.value);
  if (value === null) next.delete(key);
  else next.set(key, value);
  chosen.value = next;
  vector.value = buildVector(next, props.version, vector.value);
}

function accept() {
  const text = typed.value.trim();
  vector.value = text === "" ? null : text;
}

let latest = 0;
async function rate(text: string | null) {
  const mine = ++latest;
  if (text === null) {
    score.value = null;
    problem.value = "";
    return;
  }
  try {
    const found = await api<CvssScore>("GET", `/api/cvss/score?vector=${encodeURIComponent(text)}`);
    if (mine !== latest) return;
    score.value = found;
    problem.value = "";
  } catch (error) {
    if (mine !== latest) return;
    score.value = null;
    problem.value = describe(error);
  }
}

watch(
  vector,
  (now) => {
    typed.value = now ?? "";
    chosen.value = parseVector(now, props.version);
    void rate(now);
  },
  { immediate: true },
);
</script>

<template>
  <section :aria-label="`CVSS ${version}`">
    <div class="bs-metrics">
      <v-select
        v-for="metric in CVSS_VERSIONS[version].metrics"
        :key="metric.key"
        :model-value="chosen.get(metric.key) ?? null"
        :items="metric.options"
        :label="`${metric.name} (${metric.key})`"
        item-title="title"
        item-value="value"
        clearable
        hide-details
        density="compact"
        @update:model-value="pick(metric.key, $event)"
      />
    </div>
    <v-text-field
      v-model="typed"
      :label="`CVSS ${version} vector`"
      class="mt-3"
      density="comfortable"
      clearable
      :error-messages="problem"
      hint="Pick the metrics above, or paste a vector."
      persistent-hint
      @blur="accept"
      @keydown.enter.prevent="accept"
      @click:clear="accept"
    />
    <p v-if="score" class="mt-2" role="status">
      <v-chip :color="SEVERITY_COLORS[score.severity]" label variant="tonal">
        {{ score.score }} · {{ SEVERITY_LABELS[score.severity] }}
      </v-chip>
    </p>
  </section>
</template>

<style scoped>
.bs-metrics {
  display: grid;
  gap: 0.5rem 0.75rem;
  grid-template-columns: repeat(auto-fit, minmax(min(13rem, 100%), 1fr));
}
</style>

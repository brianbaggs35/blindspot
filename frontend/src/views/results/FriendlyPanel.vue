<script setup lang="ts">
import type { Friendly } from "../../api/types";
import { SEVERITY_COLORS, SEVERITY_LABELS, withTerms } from "../../results";

// The result in plain words: what was found, why it matters and what to do, with a tooltip on
// each technical term. Everything here comes from templates, never from the tool's own text.
defineProps<{ friendly: Friendly }>();

const GRADE_COLORS: Record<string, string> = {
  A: "success",
  B: "success",
  C: "warning",
  D: "error",
  F: "error",
};
</script>

<template>
  <section aria-label="Friendly view">
    <h2 class="text-h6 mb-2">{{ friendly.headline }}</h2>
    <ul class="mb-4">
      <li v-for="line in friendly.summary" :key="line" class="text-body-1">
        <template v-for="(part, index) in withTerms(line, friendly.terms)" :key="index">
          <v-tooltip v-if="part.meaning" :text="part.meaning" location="top">
            <template #activator="{ props: tip }">
              <button v-bind="tip" type="button" class="bs-term">{{ part.text }}</button>
            </template>
          </v-tooltip>
          <template v-else>{{ part.text }}</template>
        </template>
      </li>
    </ul>

    <v-card v-if="friendly.visuals.tls_grade" border class="mb-4">
      <v-card-item title="Encryption grade" subtitle="From the worst thing the TLS checks found">
        <template #append>
          <v-chip
            :color="GRADE_COLORS[friendly.visuals.tls_grade] ?? 'default'"
            size="x-large"
            label
            :aria-label="`Grade ${friendly.visuals.tls_grade}`"
          >
            {{ friendly.visuals.tls_grade }}
          </v-chip>
        </template>
      </v-card-item>
    </v-card>

    <v-card v-for="host in friendly.visuals.port_map" :key="host.address" border class="mb-4">
      <v-card-item :title="host.address" :subtitle="`Host is ${host.state}`" />
      <v-card-text>
        <p v-if="host.ports.length === 0" class="text-body-2">No ports were reported.</p>
        <ul v-else class="bs-ports" :aria-label="`Ports on ${host.address}`">
          <li v-for="port in host.ports" :key="`${port.protocol}${String(port.port)}`">
            <v-chip :color="port.state === 'open' ? 'success' : 'default'" label size="small">
              {{ port.port }}/{{ port.protocol }}
            </v-chip>
            <span class="ms-2">
              {{ port.state }}<template v-if="port.service"> · {{ port.service }}</template
              ><template v-if="port.software"> · {{ port.software }}</template>
            </span>
          </li>
        </ul>
      </v-card-text>
    </v-card>

    <v-card v-if="friendly.visuals.scorecard.length > 0" border class="mb-4">
      <v-card-item title="Header scorecard" />
      <v-list density="compact" role="list" aria-label="Header scorecard">
        <v-list-item v-for="item in friendly.visuals.scorecard" :key="item.name" :title="item.name">
          <template #append>
            <v-chip :color="item.passed ? 'success' : 'error'" size="small" label>
              {{ item.passed ? "Good" : "Needs work" }}
            </v-chip>
          </template>
        </v-list-item>
      </v-list>
    </v-card>

    <v-card v-for="(card, index) in friendly.cards" :key="index" border class="mb-3">
      <v-card-item
        :title="card.title"
        v-bind="card.target === null ? {} : { subtitle: card.target }"
      >
        <template #append>
          <v-chip :color="SEVERITY_COLORS[card.severity]" size="small" label variant="tonal">
            {{ SEVERITY_LABELS[card.severity] }}
          </v-chip>
        </template>
      </v-card-item>
      <v-card-text>
        <dl class="bs-advice">
          <template
            v-for="[label, text] in [
              ['What this means', card.what],
              ['Why it matters', card.why],
              ['What to do', card.todo],
            ] as const"
            :key="label"
          >
            <dt class="text-subtitle-2">{{ label }}</dt>
            <dd class="text-body-2 mb-2">
              <template v-for="(part, at) in withTerms(text, friendly.terms)" :key="at">
                <v-tooltip v-if="part.meaning" :text="part.meaning" location="top">
                  <template #activator="{ props: tip }">
                    <button v-bind="tip" type="button" class="bs-term">{{ part.text }}</button>
                  </template>
                </v-tooltip>
                <template v-else>{{ part.text }}</template>
              </template>
            </dd>
          </template>
        </dl>
      </v-card-text>
    </v-card>
    <p v-if="friendly.hidden_cards > 0" class="text-body-2">
      {{ friendly.hidden_cards }} more, less serious, are in the technical view.
    </p>
  </section>
</template>

<style scoped>
.bs-term {
  background: none;
  border: 0;
  border-bottom: 1px dotted currentColor;
  color: inherit;
  cursor: help;
  font: inherit;
  padding: 0;
}
.bs-ports {
  list-style: none;
  padding: 0;
}
.bs-ports li {
  align-items: center;
  display: flex;
  margin-block: 0.25rem;
}
.bs-advice dt {
  margin-top: 0.25rem;
}
.bs-advice dd {
  margin-inline-start: 0;
}
</style>

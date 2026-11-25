<script setup lang="ts">
import { mdiFormatListBulleted, mdiViewGridOutline } from "@mdi/js";
import { computed, ref } from "vue";
import {
  RISKS,
  RISK_COLORS,
  RISK_LABELS,
  dollars,
  percent,
  pruneTree,
  testRows,
} from "../../agents";
import type { AgentNode, RiskClass } from "../../api/types";
import { formatWhen } from "../../format";

const props = defineProps<{ root: AgentNode }>();

const layout = ref<"tree" | "grid">("tree");
const query = ref("");
const risk = ref<RiskClass | null>(null);

const shown = computed(() => pruneTree(props.root, query.value, risk.value));
const rows = computed(() => testRows(shown.value));
const testCount = computed(() => rows.value.length);

const headers = [
  { title: "Test", key: "name" },
  { title: "Category", key: "category" },
  { title: "Risk", key: "risk" },
  { title: "Runs", key: "runs" },
  { title: "Success", key: "success" },
  { title: "Cost per run", key: "cost" },
  { title: "Last run", key: "last" },
];

function state(node: AgentNode): string {
  return node.stats.active ? "Working now" : node.stats.runs > 0 ? "Idle" : "Never run";
}

const tableItems = computed(() =>
  rows.value.map(({ node, category }) => ({
    id: node.id,
    name: `${node.id} ${node.name}`,
    category,
    risk: node.risk_class,
    runs: node.stats.runs,
    success: percent(node.stats.success_rate),
    cost: dollars(node.stats.cost_per_run_usd),
    last: node.stats.last_run ? formatWhen(node.stats.last_run) : "—",
  })),
);
</script>

<template>
  <section aria-label="Agent hierarchy">
    <v-card border class="mb-4">
      <v-card-item :title="root.name" subtitle="Plans the pentest in code and hands the work out">
        <template #append>
          <v-chip :color="root.stats.active ? 'primary' : undefined" size="small">
            {{ state(root) }}
          </v-chip>
        </template>
      </v-card-item>
      <v-card-text class="text-body-2">
        {{ root.stats.runs }} {{ root.stats.runs === 1 ? "mission" : "missions" }} run · success
        {{ percent(root.stats.success_rate) }} · {{ dollars(root.stats.cost_per_run_usd) }}
        per mission
      </v-card-text>
    </v-card>

    <div class="d-flex flex-wrap align-center ga-2 mb-3">
      <v-text-field
        v-model="query"
        label="Search agents"
        hide-details
        clearable
        density="comfortable"
        class="bs-agent-search"
      />
      <v-select
        v-model="risk"
        :items="RISKS.map((one) => ({ title: RISK_LABELS[one], value: one }))"
        label="Risk"
        clearable
        hide-details
        density="comfortable"
        class="bs-agent-risk"
      />
      <v-spacer />
      <v-btn-toggle v-model="layout" mandatory density="comfortable" variant="outlined" divided>
        <v-btn value="tree" :prepend-icon="mdiFormatListBulleted">Tree</v-btn>
        <v-btn value="grid" :prepend-icon="mdiViewGridOutline">Grid</v-btn>
      </v-btn-toggle>
    </div>
    <p class="text-body-2 text-medium-emphasis mb-2">
      {{ testCount }} {{ testCount === 1 ? "test agent" : "test agents" }} shown.
    </p>

    <v-sheet v-if="testCount === 0" border rounded="lg" class="pa-6 text-center">
      <p class="text-body-1">No agent matches that.</p>
    </v-sheet>

    <v-expansion-panels v-else-if="layout === 'tree'" multiple>
      <v-expansion-panel v-for="category in shown.children" :key="category.id">
        <v-expansion-panel-title>
          <div class="bs-category-title">
            <span class="font-weight-medium">{{ category.name }}</span>
            <span class="text-body-2 text-medium-emphasis">
              {{ category.children.length }} tests · {{ state(category) }}
            </span>
          </div>
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <ul class="bs-agent-list">
            <li v-for="test in category.children" :key="test.id" :aria-label="test.id">
              <div class="d-flex flex-wrap align-center ga-2">
                <strong>{{ test.id }}</strong>
                <span>{{ test.name }}</span>
                <v-chip
                  v-if="test.risk_class"
                  :color="RISK_COLORS[test.risk_class]"
                  size="x-small"
                  variant="tonal"
                >
                  {{ test.risk_class }}
                </v-chip>
                <v-chip size="x-small" :color="test.stats.active ? 'primary' : undefined">
                  {{ state(test) }}
                </v-chip>
              </div>
              <p class="text-body-2 text-medium-emphasis">
                {{ test.stats.runs }} runs · success {{ percent(test.stats.success_rate) }} ·
                {{ dollars(test.stats.cost_per_run_usd) }} per run
                <template v-if="test.tools.length > 0"
                  >· tools: {{ test.tools.join(", ") }}</template
                >
              </p>
            </li>
          </ul>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <v-data-table
      v-else
      :headers="headers"
      :items="tableItems"
      item-value="id"
      density="comfortable"
      aria-label="Test agents"
    >
      <template #[`item.risk`]="{ value }">
        <v-chip
          v-if="value"
          :color="RISK_COLORS[value as RiskClass]"
          size="x-small"
          variant="tonal"
        >
          {{ value }}
        </v-chip>
      </template>
    </v-data-table>
  </section>
</template>

<style scoped>
.bs-agent-search {
  max-width: 22rem;
  min-width: min(14rem, 100%);
}
.bs-agent-risk {
  max-width: 24rem;
  min-width: min(14rem, 100%);
}
.bs-category-title {
  display: flex;
  flex-direction: column;
}
.bs-agent-list {
  list-style: none;
  padding: 0;
}
.bs-agent-list li + li {
  margin-top: 0.75rem;
}
</style>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { api, describe } from "../api/client";
import type { AgentSettings, AgentsOverview } from "../api/types";
import PageHeader from "../components/PageHeader.vue";
import StateView from "../components/StateView.vue";
import { useAuthStore } from "../stores/auth";
import AgentCatalog from "./agents/AgentCatalog.vue";
import AgentDefaults from "./agents/AgentDefaults.vue";
import PromptsPanel from "./agents/PromptsPanel.vue";

const auth = useAuthStore();
const canEdit = computed(() => auth.isAdmin);

const tab = ref<"agents" | "defaults" | "prompts">("agents");
const overview = ref<AgentsOverview | null>(null);
const settings = ref<AgentSettings | null>(null);
const methodology = ref<string | null>(null);
const state = ref<"loading" | "empty" | "error" | "ready">("loading");
const failure = ref("");
const notice = ref("");
const noticeOpen = ref(false);

function tell(message: string) {
  notice.value = message;
  noticeOpen.value = true;
}

// A choice made quickly must not show the answer to an older one.
let latest = 0;
async function load(quiet = false) {
  const mine = ++latest;
  if (!quiet) state.value = "loading";
  try {
    const query = methodology.value ? `?methodology=${encodeURIComponent(methodology.value)}` : "";
    const [found, current] = await Promise.all([
      api<AgentsOverview>("GET", `/api/agents/overview${query}`),
      api<AgentSettings>("GET", "/api/agents/settings"),
    ]);
    if (mine !== latest) return;
    overview.value = found;
    settings.value = current;
    methodology.value = found.methodology_id;
    state.value = "ready";
  } catch (error) {
    if (mine !== latest) return;
    failure.value = describe(error);
    state.value = "error";
  }
}

async function changed(message: string) {
  tell(message);
  await load(true);
}

onMounted(() => load());
watch(methodology, (next, before) => {
  if (before !== null && next !== before) void load(true);
});
</script>

<template>
  <PageHeader
    title="Agents"
    subtitle="The commander, a category agent for each category and a test agent for each test, with the caps and prompts they start from"
  />

  <v-alert
    v-if="overview && !overview.runner_ready"
    type="info"
    variant="tonal"
    class="mb-4"
    title="No tool runner is connected yet"
  >
    Agents cannot run tools until one is, so a mission cannot start. Everything here can still be
    set up.
  </v-alert>

  <v-tabs v-model="tab" class="mb-4" aria-label="Agents sections">
    <v-tab value="agents">Agents</v-tab>
    <v-tab value="defaults">Defaults and presets</v-tab>
    <v-tab value="prompts">Prompts</v-tab>
  </v-tabs>

  <StateView
    :state="state"
    title="Could not load the agents"
    :message="failure"
    action-label="Try again"
    @action="load()"
  >
    <template v-if="overview && settings">
      <v-sheet
        v-if="tab === 'agents' && !overview.commander"
        border
        rounded="lg"
        class="pa-6 text-center"
      >
        <p class="text-body-1">
          No methodology is turned on, so there are no agents to show. Turn one on in Methodologies.
        </p>
      </v-sheet>
      <div v-else-if="tab === 'agents' && overview.commander">
        <v-select
          v-model="methodology"
          :items="overview.methodologies.map((one) => ({ title: one.name, value: one.id }))"
          label="Methodology"
          hide-details
          density="comfortable"
          class="bs-method mb-4"
        />
        <AgentCatalog :root="overview.commander" />
      </div>
      <AgentDefaults
        v-else-if="tab === 'defaults'"
        :settings="settings"
        :can-edit="canEdit"
        @saved="changed"
      />
      <PromptsPanel
        v-else-if="tab === 'prompts'"
        :prompts="settings.prompts"
        :max-prompt="settings.max_prompt"
        :can-edit="canEdit"
        @changed="changed"
      />
    </template>
  </StateView>

  <v-snackbar v-model="noticeOpen" timeout="5000" role="status">{{ notice }}</v-snackbar>
</template>

<style scoped>
.bs-method {
  max-width: 28rem;
}
</style>

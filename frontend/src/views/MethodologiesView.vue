<script setup lang="ts">
import { mdiFolderRefresh, mdiMagnify, mdiUpdate } from "@mdi/js";
import { computed, onMounted, ref, watch } from "vue";
import { api, describe } from "../api/client";
import type { Methodology, MethodologyDetail, ReloadResult, RiskClass } from "../api/types";
import PageHeader from "../components/PageHeader.vue";
import StateView from "../components/StateView.vue";
import { matching, RISKS, SOURCES } from "../methodologies";
import { useAuthStore } from "../stores/auth";
import TestDialog from "./methodologies/TestDialog.vue";
import UpdatesDialog from "./methodologies/UpdatesDialog.vue";

const auth = useAuthStore();
const canEdit = computed(() => auth.isAdmin);

const list = ref<Methodology[]>([]);
const detail = ref<MethodologyDetail | null>(null);
const chosen = ref<string | null>(null);
const state = ref<"loading" | "error" | "ready">("loading");
const failure = ref("");
const notice = ref("");
const noticeOpen = ref(false);
const text = ref("");
const risks = ref<RiskClass[]>([]);

function tell(message: string) {
  notice.value = message;
  noticeOpen.value = true;
}

// The first load shows the page's skeleton; later ones refresh in place.
let latest = 0;
async function load(quiet = false) {
  const mine = ++latest;
  if (!quiet) state.value = "loading";
  try {
    const all = await api<Methodology[]>("GET", "/api/methodologies");
    const id = all.find((one) => one.id === chosen.value)?.id ?? all[0]?.id ?? null;
    const full = id ? await api<MethodologyDetail>("GET", `/api/methodologies/${id}`) : null;
    if (mine !== latest) return;
    list.value = all;
    chosen.value = id;
    detail.value = full;
    state.value = "ready";
  } catch (error) {
    if (mine !== latest) return;
    failure.value = describe(error);
    state.value = "error";
  }
}

// Choosing another tab loads that methodology.
watch(chosen, (id) => {
  if (id !== null && id !== detail.value?.id) void load(true);
});

const categories = computed(() =>
  (detail.value?.category_list ?? [])
    .map((category) => ({
      ...category,
      shown: matching(category.tests, { text: text.value, risks: risks.value }),
    }))
    .filter((category) => category.shown.length > 0),
);
const shownCount = computed(() => categories.value.reduce((sum, one) => sum + one.shown.length, 0));

const testId = ref("");
const testOpen = ref(false);
function openTest(id: string) {
  testId.value = id;
  testOpen.value = true;
}

const updatesOpen = ref(false);
async function applied(next: Methodology) {
  await load(true);
  tell(`${next.name} is now ${next.version_label}.`);
}

const busy = ref(false);
async function reload() {
  busy.value = true;
  try {
    const found = await api<ReloadResult>("POST", "/api/methodologies/reload");
    const problems = Object.entries(found.problems).map(([name, why]) => `${name}: ${why}`);
    await load(true);
    const parts = [
      found.added.length > 0 ? `Added ${found.added.join(", ")}.` : "No new packs.",
      found.updates_available.length > 0
        ? `Updates are waiting for ${found.updates_available.join(", ")}.`
        : "",
      ...problems,
    ];
    tell(parts.filter((part) => part !== "").join(" "));
  } catch (error) {
    tell(describe(error));
  } finally {
    busy.value = false;
  }
}

async function toggle(on: boolean | null) {
  if (detail.value === null) return;
  const { id, name } = detail.value;
  try {
    await api("PATCH", `/api/methodologies/${id}`, { enabled: on === true });
    await load(true);
    tell(on ? `${name} is on.` : `${name} is off.`);
  } catch (error) {
    tell(describe(error));
    await load(true);
  }
}

onMounted(() => load());
</script>

<template>
  <v-container>
    <PageHeader
      title="Methodologies"
      subtitle="What each test checks, and exactly what its agent is told to do."
    >
      <template #actions>
        <template v-if="canEdit">
          <v-btn :prepend-icon="mdiFolderRefresh" :loading="busy" @click="reload">
            Read packs folder
          </v-btn>
          <v-btn
            color="primary"
            :prepend-icon="mdiUpdate"
            :disabled="detail === null"
            @click="updatesOpen = true"
          >
            Check for updates
          </v-btn>
        </template>
      </template>
    </PageHeader>

    <StateView
      :state="state === 'ready' && detail === null ? 'empty' : state"
      :title="state === 'error' ? 'Could not load the methodologies' : 'No methodologies'"
      :message="state === 'error' ? failure : 'None is installed.'"
      :action-label="state === 'error' ? 'Try again' : undefined"
      @action="load()"
    >
      <template v-if="detail">
        <v-tabs v-if="list.length > 1" v-model="chosen" class="mb-4" aria-label="Methodologies">
          <v-tab v-for="one in list" :key="one.id" :value="one.id">{{ one.name }}</v-tab>
        </v-tabs>

        <v-card class="mb-4" variant="tonal">
          <v-card-title>{{ detail.name }}</v-card-title>
          <v-card-text>
            <div class="d-flex flex-wrap ga-2 mb-3">
              <v-chip size="small">{{ detail.categories }} categories</v-chip>
              <v-chip size="small">{{ detail.tests }} tests</v-chip>
              <v-chip size="small" :title="SOURCES.authored.hint">
                {{ detail.authored_playbooks }} hand-written playbooks
              </v-chip>
              <v-chip v-if="detail.custom_playbooks > 0" size="small" :title="SOURCES.custom.hint">
                {{ detail.custom_playbooks }} changed here
              </v-chip>
              <v-chip size="small">{{ detail.manual_review_tests }} reviewed by a person</v-chip>
              <v-chip size="small" variant="outlined">
                {{ detail.version_label }} (version {{ detail.version_number }})
              </v-chip>
              <v-chip size="small" variant="outlined">Licence: {{ detail.license }}</v-chip>
            </div>
            <a :href="detail.source_url" target="_blank" rel="noopener noreferrer">
              Where it comes from
            </a>
            <v-switch
              v-if="canEdit"
              :model-value="detail.enabled"
              label="Offer this methodology for new pentests"
              color="primary"
              hide-details
              class="mt-2"
              @update:model-value="toggle"
            />
          </v-card-text>
        </v-card>

        <div class="d-flex flex-wrap align-center ga-4 mb-4">
          <v-text-field
            v-model="text"
            label="Search tests, ids and tools"
            :prepend-inner-icon="mdiMagnify"
            clearable
            hide-details
            density="comfortable"
            class="search"
          />
          <v-btn-toggle
            v-model="risks"
            multiple
            divided
            variant="outlined"
            color="primary"
            density="comfortable"
            role="group"
            aria-label="Risk class"
          >
            <v-btn
              v-for="(info, risk) in RISKS"
              :key="risk"
              :value="risk"
              :title="info.hint"
              :aria-pressed="risks.includes(risk)"
            >
              {{ info.label }}
            </v-btn>
          </v-btn-toggle>
        </div>

        <v-alert v-if="categories.length === 0" type="info" variant="tonal">
          No test matches that search.
        </v-alert>
        <p v-else class="text-body-2 mb-2">Showing {{ shownCount }} of {{ detail.tests }} tests.</p>
        <v-expansion-panels multiple variant="accordion">
          <v-expansion-panel v-for="category in categories" :key="category.id">
            <v-expansion-panel-title>
              <span class="font-weight-medium">{{ category.name }}</span>
              <span class="text-medium-emphasis ms-3">{{ category.shown.length }} tests</span>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <v-list density="comfortable">
                <v-list-item
                  v-for="test in category.shown"
                  :key="test.id"
                  :title="test.name"
                  :subtitle="test.id"
                  :aria-label="`${test.id} ${test.name}`"
                  @click="openTest(test.id)"
                >
                  <template #append>
                    <v-chip :color="RISKS[test.risk_class].color" size="small" variant="tonal">
                      {{ RISKS[test.risk_class].label }}
                    </v-chip>
                    <v-chip
                      v-if="test.playbook_source !== 'generated'"
                      size="small"
                      variant="outlined"
                      class="ms-2"
                    >
                      {{ SOURCES[test.playbook_source].label }}
                    </v-chip>
                  </template>
                </v-list-item>
              </v-list>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </template>
    </StateView>

    <TestDialog
      v-if="detail && testId"
      v-model="testOpen"
      :methodology-id="detail.id"
      :test-id="testId"
      :can-edit="canEdit"
      @changed="load(true)"
    />
    <UpdatesDialog v-if="detail" v-model="updatesOpen" :methodology="detail" @applied="applied" />
    <v-snackbar v-model="noticeOpen" :timeout="6000">{{ notice }}</v-snackbar>
  </v-container>
</template>

<style scoped>
.search {
  max-width: 24rem;
  min-width: min(16rem, 100%);
}
</style>

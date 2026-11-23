<script setup lang="ts">
import { mdiOpenInNew } from "@mdi/js";
import { computed, ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { TestDetail } from "../../api/types";
import { RISKS, SOURCES } from "../../methodologies";
import PlaybookDialog from "./PlaybookDialog.vue";

// One test: what it is for, and the playbook its agent is given.
const props = defineProps<{ methodologyId: string; testId: string; canEdit: boolean }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ changed: [] }>();

const detail = ref<TestDetail | null>(null);
const failure = ref("");
const busy = ref(false);
const editing = ref(false);

let latest = 0;
async function load() {
  const mine = ++latest;
  failure.value = "";
  try {
    const found = await api<TestDetail>(
      "GET",
      `/api/methodologies/${props.methodologyId}/tests/${props.testId}`,
    );
    if (mine === latest) detail.value = found;
  } catch (error) {
    if (mine === latest) failure.value = describe(error);
  }
}

// Immediate, because the page mounts this dialog already open, the first time a test is chosen.
watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    detail.value = null;
    void load();
  },
  { immediate: true },
);

// The lists of steps, leaving out the ones the playbook does not have.
const steps = computed(() => {
  const playbook = detail.value?.test.playbook;
  if (!playbook) return [];
  return [
    { title: "Safe steps", items: playbook.safe_steps },
    { title: "Active steps", items: playbook.active_steps },
    { title: "Intrusive steps, only after approval", items: playbook.intrusive_steps },
  ].filter((step) => step.items.length > 0);
});

function saved(next: TestDetail) {
  detail.value = next;
  emit("changed");
}

async function putBack() {
  busy.value = true;
  failure.value = "";
  try {
    await api("DELETE", `/api/methodologies/${props.methodologyId}/tests/${props.testId}/playbook`);
    emit("changed");
    await load();
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="860" scrollable>
    <v-card :title="detail ? `${detail.test.id} · ${detail.test.name}` : 'Loading the test'">
      <v-card-text>
        <v-alert v-if="failure" type="error" variant="tonal" class="mb-4" role="alert">
          {{ failure }}
        </v-alert>
        <v-skeleton-loader v-if="!detail && !failure" type="article" />
        <template v-if="detail">
          <div class="d-flex flex-wrap ga-2 mb-4">
            <v-chip :color="RISKS[detail.test.risk_class].color" size="small" variant="tonal">
              {{ RISKS[detail.test.risk_class].label }}
            </v-chip>
            <v-chip size="small" variant="tonal">{{ detail.category_name }}</v-chip>
            <v-chip
              size="small"
              variant="outlined"
              :title="SOURCES[detail.test.playbook_source].hint"
            >
              {{ SOURCES[detail.test.playbook_source].label }}
            </v-chip>
            <v-chip v-if="detail.test.playbook.manual_review" size="small" variant="outlined">
              A person reviews the result
            </v-chip>
            <v-chip
              v-for="need in detail.test.requires"
              :key="need"
              size="small"
              variant="outlined"
            >
              only if the target has {{ need }}
            </v-chip>
          </div>
          <a
            v-if="detail.test.reference"
            :href="detail.test.reference"
            target="_blank"
            rel="noopener noreferrer"
            class="d-inline-flex align-center ga-1 mb-4"
          >
            Read the test in its guide
            <v-icon :icon="mdiOpenInNew" size="small" />
          </a>

          <h3 class="text-subtitle-1 mb-1">Objectives</h3>
          <ul class="mb-4 ps-6">
            <li v-for="goal in detail.test.objectives" :key="goal">{{ goal }}</li>
          </ul>

          <h3 class="text-subtitle-1 mb-1">What the agent is told</h3>
          <p class="mb-2">{{ detail.test.playbook.summary }}</p>
          <pre class="playbook-text mb-4">{{ detail.test.playbook.instructions }}</pre>

          <h3 class="text-subtitle-1 mb-1">Tools</h3>
          <div class="d-flex flex-wrap ga-2 mb-4">
            <v-chip v-for="tool in detail.test.playbook.tools" :key="tool" size="small" label>
              {{ tool }}
            </v-chip>
            <span v-if="detail.test.playbook.tools.length === 0" class="text-medium-emphasis">
              None: this test is done by the agent with the browser and the HTTP client.
            </span>
          </div>

          <template v-for="step in steps" :key="step.title">
            <h3 class="text-subtitle-1 mb-1">{{ step.title }}</h3>
            <ul class="mb-4 ps-6">
              <li v-for="item in step.items" :key="item">{{ item }}</li>
            </ul>
          </template>

          <h3 class="text-subtitle-1 mb-1">Evidence it must bring back</h3>
          <ul class="mb-4 ps-6">
            <li v-for="item in detail.test.playbook.evidence" :key="item">{{ item }}</li>
          </ul>

          <h3 class="text-subtitle-1 mb-1">Passed when</h3>
          <p class="mb-4">{{ detail.test.playbook.success }}</p>
          <h3 class="text-subtitle-1 mb-1">A finding when</h3>
          <p class="mb-4">{{ detail.test.playbook.failure }}</p>
          <template v-if="detail.test.playbook.not_applicable.length > 0">
            <h3 class="text-subtitle-1 mb-1">Not applicable when</h3>
            <ul class="mb-2 ps-6">
              <li v-for="item in detail.test.playbook.not_applicable" :key="item">{{ item }}</li>
            </ul>
          </template>
        </template>
      </v-card-text>
      <v-card-actions>
        <template v-if="canEdit && detail">
          <v-btn color="primary" variant="tonal" @click="editing = true">Edit the playbook</v-btn>
          <v-btn v-if="detail.test.playbook_source === 'custom'" :loading="busy" @click="putBack">
            Put the original back
          </v-btn>
        </template>
        <v-spacer />
        <v-btn @click="open = false">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
  <PlaybookDialog
    v-if="detail"
    v-model="editing"
    :methodology-id="methodologyId"
    :test-id="testId"
    :playbook="detail.test.playbook"
    @saved="saved"
  />
</template>

<style scoped>
.playbook-text {
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 0.875rem;
  line-height: 1.5;
}
</style>

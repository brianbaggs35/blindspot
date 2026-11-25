<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { BUDGET_FIELDS, RISK_COLORS, RISK_LABELS, budgetProblem, dollars } from "../../agents";
import { api, describe } from "../../api/client";
import type {
  AgentSettings,
  AgentsOverview,
  Budget,
  Mission,
  MissionPreview,
  Pentest,
  StartRequest,
} from "../../api/types";

const props = defineProps<{ pentest: Pentest; runnerReady: boolean }>();
const emit = defineEmits<{ started: [mission: Mission] }>();
const open = defineModel<boolean>({ required: true });

const step = ref<"choose" | "caps" | "review">("choose");
const settings = ref<AgentSettings | null>(null);
const picks = ref<{ title: string; value: string }[]>([]);
const preset = ref("safe-full");
const only = ref<string[]>([]);
const budget = ref<Budget | null>(null);
const preview = ref<MissionPreview | null>(null);
const confirmed = ref(false);
const busy = ref(false);
const failure = ref("");

const problem = computed(() => (budget.value ? budgetProblem(budget.value) : ""));

function request(): StartRequest {
  const body: StartRequest = { preset: preset.value };
  if (only.value.length > 0) body.only = only.value;
  if (budget.value) body.budget = budget.value;
  return body;
}

async function begin() {
  step.value = "choose";
  confirmed.value = false;
  failure.value = "";
  preview.value = null;
  only.value = [];
  busy.value = true;
  try {
    const [current, tree] = await Promise.all([
      api<AgentSettings>("GET", "/api/agents/settings"),
      api<AgentsOverview>(
        "GET",
        `/api/agents/overview?methodology=${encodeURIComponent(props.pentest.methodology_id)}`,
      ),
    ]);
    settings.value = current;
    budget.value = null;
    picks.value = (tree.commander?.children ?? []).flatMap((category) => [
      { title: `Category: ${category.name}`, value: category.id },
      ...category.children.map((test) => ({ title: `${test.id} ${test.name}`, value: test.id })),
    ]);
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}

watch(open, (now) => {
  if (now) void begin();
});

const chosen = computed(() => settings.value?.presets.find((one) => one.id === preset.value));

function toCaps() {
  // The caps start from the preset, and a person may change them before the review.
  budget.value = chosen.value ? { ...chosen.value.budget } : null;
  step.value = "caps";
}

async function toReview() {
  busy.value = true;
  failure.value = "";
  try {
    preview.value = await api<MissionPreview>(
      "POST",
      `/api/pentests/${props.pentest.id}/missions/preview`,
      request(),
    );
    step.value = "review";
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}

async function start() {
  busy.value = true;
  failure.value = "";
  try {
    const made = await api<Mission>("POST", `/api/pentests/${props.pentest.id}/missions`, {
      ...request(),
      confirmed: confirmed.value,
    });
    open.value = false;
    emit("started", made);
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="760" :persistent="busy" aria-label="Deploy agents">
    <v-card title="Deploy agents">
      <v-card-text>
        <v-alert v-if="failure" type="error" variant="tonal" class="mb-4" role="alert">
          {{ failure }}
        </v-alert>
        <v-alert v-if="!runnerReady" type="info" variant="tonal" class="mb-4">
          No tool runner is connected yet, so a mission cannot start. You can still look at what it
          would do.
        </v-alert>

        <template v-if="step === 'choose'">
          <h3 class="text-subtitle-1 mb-2">How far may the agents go?</h3>
          <v-radio-group v-model="preset" hide-details aria-label="Preset">
            <v-radio v-for="one in settings?.presets ?? []" :key="one.id" :value="one.id">
              <template #label>
                <div>
                  <div class="font-weight-medium">{{ one.name }}</div>
                  <div class="text-body-2 text-medium-emphasis">{{ one.summary }}</div>
                </div>
              </template>
            </v-radio>
          </v-radio-group>
          <h3 class="text-subtitle-1 mt-4 mb-2">What should they test?</h3>
          <v-autocomplete
            v-model="only"
            :items="picks"
            label="Categories or tests (leave empty for the whole methodology)"
            multiple
            chips
            closable-chips
            clearable
            density="comfortable"
          />
        </template>

        <template v-else-if="step === 'caps' && budget">
          <h3 class="text-subtitle-1 mb-2">Caps</h3>
          <p class="text-body-2 text-medium-emphasis mb-3">
            Code stops the mission at any of these. They start from the preset you chose.
          </p>
          <div class="bs-deploy-caps">
            <v-text-field
              v-for="field in BUDGET_FIELDS"
              :key="field.key"
              v-model.number="budget[field.key]"
              :label="field.label"
              :min="field.min"
              :max="field.max"
              :step="field.step"
              type="number"
              density="comfortable"
              hide-details="auto"
            />
          </div>
          <p v-if="problem" class="text-body-2 text-error mt-3" role="alert">{{ problem }}</p>
        </template>

        <template v-else-if="step === 'review' && preview">
          <h3 class="text-subtitle-1 mb-2">Review</h3>
          <ul class="bs-review">
            <li>
              <strong>{{ preview.summary.runs }}</strong> tests will run,
              <strong>{{ preview.summary.skipped }}</strong> will not.
            </li>
            <li>
              The most they may do:
              <v-chip :color="RISK_COLORS[preview.max_risk]" size="small" variant="tonal">
                {{ RISK_LABELS[preview.max_risk] }}
              </v-chip>
              (tests: {{ preview.summary.risk.safe }} safe,
              {{ preview.summary.risk.active }} active,
              {{ preview.summary.risk.intrusive }} intrusive). Intrusive steps always wait for an
              administrator.
            </li>
            <li>
              At most {{ preview.budget.steps }} steps, {{ dollars(preview.budget.cost_usd) }} of
              model spend and {{ Math.round(preview.budget.seconds / 3600) }} hours.
            </li>
            <li v-if="preview.summary.tools.length > 0">
              Tools: {{ preview.summary.tools.join(", ") }}.
            </li>
            <li v-for="skip in preview.summary.skips" :key="skip.reason">
              {{ skip.tests }} skipped: {{ skip.reason }}
            </li>
          </ul>
          <h4 class="text-subtitle-2 mt-3">Targets in scope</h4>
          <ul class="bs-review">
            <li v-for="target in preview.in_scope" :key="target">{{ target }}</li>
          </ul>
          <v-checkbox
            v-model="confirmed"
            class="mt-3"
            hide-details
            label="I confirm that everything in scope above is authorized for this testing."
          />
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn :disabled="busy" @click="open = false">Cancel</v-btn>
        <v-btn
          v-if="step !== 'choose'"
          :disabled="busy"
          @click="step = step === 'review' ? 'caps' : 'choose'"
        >
          Back
        </v-btn>
        <v-btn
          v-if="step === 'choose'"
          color="primary"
          variant="flat"
          :disabled="busy || !settings"
          @click="toCaps"
        >
          Next
        </v-btn>
        <v-btn
          v-else-if="step === 'caps'"
          color="primary"
          variant="flat"
          :loading="busy"
          :disabled="problem !== ''"
          @click="toReview"
        >
          Review
        </v-btn>
        <v-btn
          v-else
          color="primary"
          variant="flat"
          :loading="busy"
          :disabled="!confirmed || !runnerReady"
          @click="start"
        >
          Start the agents
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.bs-deploy-caps {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(auto-fit, minmax(min(14rem, 100%), 1fr));
}
.bs-review {
  padding-left: 1.25rem;
}
.bs-review li + li {
  margin-top: 0.5rem;
}
</style>

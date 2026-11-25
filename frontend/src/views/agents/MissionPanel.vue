<script setup lang="ts">
import { mdiPause, mdiPlay, mdiStop } from "@mdi/js";
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  STATUS_COLORS,
  STATUS_LABELS,
  describeEvent,
  dollars,
  duration,
  isLive,
} from "../../agents";
import { api, describe } from "../../api/client";
import type { Mission, MissionEvent, MissionStep, MissionTask } from "../../api/types";
import { formatWhen } from "../../format";

const props = defineProps<{ pentestId: string; missionId: string; canEdit: boolean }>();
const emit = defineEmits<{ changed: [] }>();

const POLL_MS = 4000;
const FINISHED = ["completed", "cancelled", "failed"];

const mission = ref<Mission | null>(null);
const tasks = ref<MissionTask[]>([]);
const waiting = ref<MissionStep[]>([]);
const events = ref<MissionEvent[]>([]);
const failure = ref("");
const busy = ref(false);
const loaded = ref(false);

const base = computed(() => `/api/pentests/${props.pentestId}/missions/${props.missionId}`);
let timer: ReturnType<typeof setTimeout> | undefined;
let alive = true;
let cursor = 0;

async function refresh() {
  try {
    const [found, steps, log] = await Promise.all([
      api<{ mission: Mission; tasks: MissionTask[] }>("GET", base.value),
      api<{ steps: MissionStep[] }>("GET", `${base.value}/steps?status=awaiting_approval`),
      api<{ events: MissionEvent[]; next_after: number }>(
        "GET",
        `${base.value}/events?after=${String(cursor)}&limit=200`,
      ),
    ]);
    if (!alive) return;
    mission.value = found.mission;
    tasks.value = found.tasks;
    waiting.value = steps.steps;
    cursor = log.next_after;
    events.value = [...events.value, ...log.events].slice(-300);
    failure.value = "";
  } catch (error) {
    if (alive) failure.value = describe(error);
  } finally {
    loaded.value = true;
  }
  if (alive && mission.value && !FINISHED.includes(mission.value.status)) {
    timer = setTimeout(() => void refresh(), POLL_MS);
  }
}

onMounted(() => void refresh());
onUnmounted(() => {
  alive = false;
  clearTimeout(timer);
});

async function send(path: string, body: object = {}) {
  busy.value = true;
  failure.value = "";
  try {
    await api("POST", `${base.value}/${path}`, body);
    clearTimeout(timer);
    await refresh();
    emit("changed");
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}

const categories = computed(() =>
  tasks.value
    .filter((one) => one.kind === "category")
    .map((category) => ({
      category,
      tests: tasks.value.filter((one) => one.parent_id === category.id),
    })),
);
const commander = computed(() => tasks.value.find((one) => one.kind === "commander"));
const nameOf = (taskId: string) => tasks.value.find((one) => one.id === taskId)?.name ?? "A test";

function words(request: Record<string, unknown>): string {
  return Object.entries(request)
    .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(", ");
}

const recent = computed(() => events.value.slice(-50).reverse());
const spent = computed(() => mission.value?.spent ?? {});
const budget = computed(() => mission.value?.budget);
</script>

<template>
  <section aria-label="Mission">
    <v-skeleton-loader v-if="!loaded" type="heading, paragraph" />
    <v-alert v-if="failure" type="error" variant="tonal" class="mb-3" role="alert">
      {{ failure }}
    </v-alert>

    <template v-if="mission && budget">
      <div class="d-flex flex-wrap align-center ga-2 mb-3">
        <v-chip :color="STATUS_COLORS[mission.status]" variant="flat">
          {{ STATUS_LABELS[mission.status] ?? mission.status }}
        </v-chip>
        <span class="text-body-2">
          {{ spent.steps ?? 0 }} of {{ budget.steps }} steps · {{ dollars(spent.cost_usd ?? 0) }} of
          {{ dollars(budget.cost_usd) }} · {{ duration(spent.seconds ?? 0) }} of
          {{ duration(budget.seconds) }}
        </span>
        <v-spacer />
        <template v-if="canEdit">
          <v-btn
            v-if="mission.status === 'running'"
            :prepend-icon="mdiPause"
            :disabled="busy"
            @click="send('pause')"
          >
            Pause
          </v-btn>
          <v-btn
            v-if="mission.status === 'paused' || mission.status === 'stopped'"
            color="primary"
            variant="flat"
            :prepend-icon="mdiPlay"
            :disabled="busy"
            @click="send('resume')"
          >
            Resume
          </v-btn>
          <v-btn
            v-if="!FINISHED.includes(mission.status) && mission.status !== 'cancelling'"
            color="error"
            variant="tonal"
            :prepend-icon="mdiStop"
            :disabled="busy"
            @click="send('cancel')"
          >
            Cancel the mission
          </v-btn>
        </template>
      </div>
      <p v-if="mission.stop_reason" class="text-body-2 mb-3">{{ mission.stop_reason }}</p>
      <p v-if="commander?.summary" class="text-body-2 text-medium-emphasis mb-3">
        {{ commander.summary }}
      </p>

      <v-card v-if="waiting.length > 0" border class="mb-4" aria-label="Steps waiting for approval">
        <v-card-item
          title="Waiting for you"
          subtitle="A step runs only after it passes the checks again"
        />
        <v-list>
          <v-list-item
            v-for="step in waiting"
            :key="step.id"
            :title="`${nameOf(step.task_id)}: ${step.tool}`"
            :subtitle="words(step.request)"
          >
            <template v-if="canEdit" #append>
              <v-btn
                size="small"
                color="primary"
                variant="tonal"
                :disabled="busy"
                @click="send(`steps/${step.id}/approve`)"
              >
                Approve
              </v-btn>
              <v-btn
                size="small"
                class="ml-2"
                variant="tonal"
                :disabled="busy"
                @click="send(`steps/${step.id}/deny`)"
              >
                Deny
              </v-btn>
            </template>
          </v-list-item>
        </v-list>
      </v-card>

      <h3 class="text-subtitle-1 mb-2">Tests</h3>
      <v-expansion-panels multiple class="mb-4">
        <v-expansion-panel v-for="{ category, tests } in categories" :key="category.id">
          <v-expansion-panel-title>
            <span class="font-weight-medium mr-3">{{ category.name }}</span>
            <v-chip size="x-small" :color="STATUS_COLORS[category.status]">
              {{ STATUS_LABELS[category.status] ?? category.status }}
            </v-chip>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <ul class="bs-tasks">
              <li v-for="test in tests" :key="test.id">
                <strong>{{ test.ref }}</strong> {{ test.name }}
                <v-chip size="x-small" :color="STATUS_COLORS[test.status]" class="ml-1">
                  {{ STATUS_LABELS[test.status] ?? test.status }}
                </v-chip>
                <p v-if="test.summary" class="text-body-2 text-medium-emphasis">
                  {{ test.summary }}
                </p>
              </li>
            </ul>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>

      <h3 class="text-subtitle-1 mb-2">Log</h3>
      <ol class="bs-log" aria-label="Mission log">
        <li v-for="event in recent" :key="event.id">
          <time class="text-caption text-medium-emphasis">{{ formatWhen(event.created_at) }}</time>
          {{ describeEvent(event) }}
        </li>
      </ol>
      <p v-if="events.length === 0 && isLive(mission.status)" class="text-body-2">
        Nothing has happened yet.
      </p>
    </template>
  </section>
</template>

<style scoped>
.bs-tasks,
.bs-log {
  list-style: none;
  padding: 0;
}
.bs-tasks li + li,
.bs-log li + li {
  margin-top: 0.5rem;
}
</style>

<script setup lang="ts">
import { mdiCogOutline, mdiPlayCircleOutline, mdiRestore } from "@mdi/js";
import { computed, onMounted, ref } from "vue";
import { api, describe } from "../api/client";
import type { RunMode, ToolSetting, ToolSettings, ToolTestResult } from "../api/types";
import PageHeader from "../components/PageHeader.vue";
import StateView from "../components/StateView.vue";
import {
  RISK_COLORS,
  RISKS,
  RUN_MODES,
  STATUS_COLORS,
  STATUS_LABELS,
  WHERE_LABELS,
  customised,
  whereOf,
} from "../tools";
import { useAuthStore } from "../stores/auth";
import ToolSettingsDialog from "./tools/ToolSettingsDialog.vue";
import ToolTestDialog from "./tools/ToolTestDialog.vue";

const auth = useAuthStore();

const settings = ref<ToolSettings | null>(null);
const state = ref<"loading" | "error" | "ready">("loading");
const failure = ref("");
const notice = ref("");
const noticeOpen = ref(false);

function tell(message: string) {
  notice.value = message;
  noticeOpen.value = true;
}

let latest = 0;
async function load(quiet = false) {
  const mine = ++latest;
  if (!quiet) state.value = "loading";
  try {
    const found = await api<ToolSettings>("GET", "/api/tools/settings");
    if (mine !== latest) return;
    settings.value = found;
    state.value = "ready";
  } catch (error) {
    if (mine !== latest) return;
    failure.value = describe(error);
    state.value = "error";
  }
}

const hint = computed(() => RUN_MODES.find((one) => one.value === settings.value?.run_mode)?.hint);

async function chooseDefault(mode: RunMode) {
  try {
    await api("PUT", "/api/tools/settings/default", { mode });
    await load(true);
    tell("The default was saved.");
  } catch (error) {
    tell(`Could not save it: ${describe(error)}`);
  }
}

const editing = ref<ToolSetting | null>(null);
const editOpen = ref(false);
function edit(tool: ToolSetting) {
  editing.value = tool;
  editOpen.value = true;
}

async function saved(tool: ToolSetting) {
  await load(true);
  tell(`Saved the settings of ${tool.name}.`);
}

async function reset(tool: ToolSetting) {
  try {
    await api("DELETE", `/api/tools/settings/${tool.id}`);
    await load(true);
    tell(`${tool.name} is back to its defaults.`);
  } catch (error) {
    tell(`Could not do that: ${describe(error)}`);
  }
}

const testName = ref("");
const testOpen = ref(false);
const testing = ref(false);
const testResult = ref<ToolTestResult | null>(null);
const testFailure = ref("");

async function test(tool: ToolSetting) {
  testName.value = tool.name;
  testResult.value = null;
  testFailure.value = "";
  testing.value = true;
  testOpen.value = true;
  try {
    testResult.value = await api<ToolTestResult>("POST", `/api/tools/settings/${tool.id}/test`);
  } catch (error) {
    testFailure.value = describe(error);
  } finally {
    testing.value = false;
  }
}

onMounted(() => load());
</script>

<template>
  <v-container>
    <PageHeader
      title="Tools"
      subtitle="How each tool runs: Local from this container or in Docker, and the limits it runs under"
    />
    <StateView
      :state="state"
      title="Could not load the tools"
      :message="failure"
      action-label="Try again"
      @action="load()"
    >
      <template v-if="settings">
        <v-alert
          v-if="!settings.docker.reachable"
          type="info"
          variant="tonal"
          class="mb-4"
          title="Docker is not connected"
        >
          {{ settings.docker.note }} Tools set to Docker cannot run until it is.
        </v-alert>

        <v-card border class="mb-4">
          <v-card-item title="Default" subtitle="For every tool that has no setting of its own" />
          <v-card-text>
            <v-select
              :model-value="settings.run_mode"
              :items="RUN_MODES"
              item-title="title"
              item-value="value"
              label="Where tools run"
              :disabled="!auth.isAdmin"
              :hint="hint"
              persistent-hint
              class="bs-default"
              @update:model-value="chooseDefault"
            />
            <p v-if="!auth.isAdmin" class="text-caption mt-2">
              Only an administrator can change these settings.
            </p>
          </v-card-text>
        </v-card>

        <v-card
          v-for="tool in settings.tools"
          :key="tool.id"
          border
          class="mb-3"
          :aria-label="tool.name"
        >
          <v-card-item>
            <v-card-title class="d-flex align-center flex-wrap ga-2">
              <span>{{ tool.name }}</span>
              <code class="text-caption">{{ tool.id }}</code>
              <v-chip size="small" label :color="RISK_COLORS[tool.risk]" variant="tonal">
                {{ RISKS.find((one) => one.value === tool.risk)?.title }}
              </v-chip>
              <v-chip size="small" label variant="outlined">{{ tool.origin }}</v-chip>
              <v-chip
                size="small"
                label
                :color="STATUS_COLORS[tool.effective.status]"
                variant="tonal"
              >
                {{ STATUS_LABELS[tool.effective.status] }}
              </v-chip>
            </v-card-title>
            <v-card-subtitle class="text-wrap">{{ tool.explain }}</v-card-subtitle>
          </v-card-item>
          <v-card-text>
            <dl class="bs-facts">
              <dt>Runs</dt>
              <dd>{{ whereOf(tool.effective) }}</dd>
              <template v-if="tool.effective.problem">
                <dt>Problem</dt>
                <dd>{{ tool.effective.problem }}</dd>
              </template>
              <template v-if="tool.effective.offer">
                <dt>Another way</dt>
                <dd>
                  It would run {{ WHERE_LABELS[tool.effective.offer] }}. Choose that in its settings
                  if you want it.
                </dd>
              </template>
              <template v-if="tool.effective.path">
                <dt>Program</dt>
                <dd>{{ tool.effective.path }}</dd>
              </template>
              <template v-if="tool.image">
                <dt>Image</dt>
                <dd class="bs-address">{{ tool.image }}</dd>
              </template>
              <dt>Limits</dt>
              <dd>
                {{ tool.limits.timeout_s }} s, {{ tool.limits.max_output_mb }} MB of output,
                {{
                  tool.limits.rate_per_s
                    ? `${tool.limits.rate_per_s} requests per second`
                    : "no rate limit"
                }}, up to {{ tool.limits.max_risk }}
              </dd>
            </dl>
          </v-card-text>
          <v-card-actions v-if="auth.isAdmin">
            <v-btn :prepend-icon="mdiCogOutline" @click="edit(tool)">Settings</v-btn>
            <v-btn
              v-if="tool.effective.mode === 'local'"
              :prepend-icon="mdiPlayCircleOutline"
              @click="test(tool)"
            >
              Test
            </v-btn>
            <v-btn v-if="customised(tool)" :prepend-icon="mdiRestore" @click="reset(tool)">
              Reset
            </v-btn>
          </v-card-actions>
        </v-card>

        <ToolSettingsDialog v-if="editing" v-model="editOpen" :tool="editing" @saved="saved" />
        <ToolTestDialog
          v-model="testOpen"
          :name="testName"
          :result="testResult"
          :failure="testFailure"
          :busy="testing"
        />
      </template>
    </StateView>
    <v-snackbar v-model="noticeOpen" timeout="5000">{{ notice }}</v-snackbar>
  </v-container>
</template>

<style scoped>
.bs-default {
  max-width: 24rem;
}
.bs-facts {
  display: grid;
  gap: 0.25rem 1rem;
  grid-template-columns: max-content 1fr;
}
.bs-facts dt {
  font-weight: 500;
}
.bs-facts dd {
  overflow-wrap: anywhere;
}
.bs-address {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
}
</style>

<script setup lang="ts">
import { mdiPlus } from "@mdi/js";
import { computed, ref, watch } from "vue";
import { PROMPT_AGENTS, lineDiff } from "../../agents";
import { api, describe } from "../../api/client";
import type { PromptBody, PromptInfo } from "../../api/types";
import { formatWhen } from "../../format";
import FormDialog from "../../components/FormDialog.vue";

const props = defineProps<{ prompts: PromptInfo[]; maxPrompt: number; canEdit: boolean }>();
const emit = defineEmits<{ changed: [message: string] }>();

const agent = ref(props.prompts[0]?.agent ?? "test-agent");
const viewing = ref(0);
const compareWith = ref<number | null>(null);
const bodies = ref<Record<string, string>>({});
const failure = ref("");
const busy = ref(false);

const info = computed(() => props.prompts.find((one) => one.agent === agent.value));
const versions = computed(() => info.value?.versions ?? []);
const key = (version: number) => `${agent.value}/${String(version)}`;

async function fetchBody(version: number): Promise<string | null> {
  const known = bodies.value[key(version)];
  if (known !== undefined) return known;
  try {
    const found = await api<PromptBody>(
      "GET",
      `/api/agents/prompts/${agent.value}/${String(version)}`,
    );
    bodies.value = { ...bodies.value, [key(version)]: found.body };
    return found.body;
  } catch (error) {
    failure.value = describe(error);
    return null;
  }
}

async function load() {
  failure.value = "";
  await Promise.all([
    fetchBody(viewing.value),
    compareWith.value === null ? null : fetchBody(compareWith.value),
  ]);
}

watch([agent, viewing, compareWith], load, { immediate: true });
watch(agent, () => {
  viewing.value = info.value?.active ?? 0;
  compareWith.value = null;
});

const text = computed(() => bodies.value[key(viewing.value)] ?? "");
const other = computed(() =>
  compareWith.value === null ? null : (bodies.value[key(compareWith.value)] ?? null),
);
const diff = computed(() => (other.value === null ? [] : lineDiff(other.value, text.value)));

function label(version: { version: number; note: string }): string {
  return version.version === 0 ? "Built in" : `Version ${String(version.version)}`;
}

const options = computed(() =>
  versions.value.map((one) => ({
    title: `${label(one)}${one.note && one.version !== 0 ? `: ${one.note}` : ""}`,
    value: one.version,
  })),
);

async function use(version: number) {
  busy.value = true;
  failure.value = "";
  try {
    await api<PromptInfo>("POST", `/api/agents/prompts/${agent.value}/activate`, { version });
    emit(
      "changed",
      version === 0
        ? "The built-in prompt is in use again."
        : `Version ${String(version)} is in use.`,
    );
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}

const adding = ref(false);
const newBody = ref("");
const newNote = ref("");
const newUse = ref(true);
const addFailure = ref("");

function openAdd() {
  newBody.value = text.value;
  newNote.value = "";
  newUse.value = true;
  addFailure.value = "";
  adding.value = true;
}

async function add() {
  busy.value = true;
  addFailure.value = "";
  try {
    const made = await api<PromptInfo>("POST", `/api/agents/prompts/${agent.value}`, {
      body: newBody.value,
      note: newNote.value,
      activate: newUse.value,
    });
    adding.value = false;
    viewing.value = made.versions[made.versions.length - 1]?.version ?? 0;
    emit("changed", "A new version was added.");
  } catch (error) {
    addFailure.value = describe(error);
  } finally {
    busy.value = false;
  }
}

const tooShort = computed(() => newBody.value.trim().length < 20);
const tooLong = computed(() => newBody.value.length > props.maxPrompt);
</script>

<template>
  <section aria-label="Prompts">
    <p class="text-body-2 text-medium-emphasis mb-3">
      A prompt is never edited: a change adds a version. A mission keeps the version it started
      with, so changing a prompt never changes a mission that is running. Safety does not depend on
      a prompt: the scope guard, the permission policy and the caps are code.
    </p>
    <v-alert v-if="failure" type="error" variant="tonal" class="mb-3" role="alert">
      {{ failure }}
    </v-alert>

    <v-btn-toggle
      v-model="agent"
      mandatory
      density="comfortable"
      variant="outlined"
      divided
      class="mb-4"
    >
      <v-btn v-for="one in prompts" :key="one.agent" :value="one.agent">
        {{ PROMPT_AGENTS[one.agent] ?? one.agent }}
      </v-btn>
    </v-btn-toggle>
    <p v-if="info" class="text-body-2 mb-3">{{ info.label }}</p>

    <v-list v-if="info" lines="two" border rounded aria-label="Versions" class="mb-4">
      <v-list-item
        v-for="one in versions"
        :key="one.version"
        :title="label(one)"
        :subtitle="
          [one.note, one.created_by, one.created_at ? formatWhen(one.created_at) : '']
            .filter((part) => part !== '')
            .join(' · ')
        "
        :active="viewing === one.version"
        @click="viewing = one.version"
      >
        <template #append>
          <v-chip v-if="one.active" color="success" size="small" class="mr-2">In use</v-chip>
          <v-btn
            v-if="canEdit && !one.active"
            size="small"
            variant="tonal"
            :disabled="busy"
            :aria-label="`Use ${label(one)}`"
            @click.stop="use(one.version)"
          >
            Use this
          </v-btn>
        </template>
      </v-list-item>
    </v-list>

    <div class="d-flex flex-wrap align-center ga-2 mb-2">
      <v-select
        v-model="compareWith"
        :items="options"
        label="Compare with"
        clearable
        hide-details
        density="comfortable"
        class="bs-compare"
      />
      <v-spacer />
      <v-btn
        v-if="canEdit && info && info.active !== 0"
        variant="tonal"
        :disabled="busy"
        @click="use(0)"
      >
        Put back the built-in prompt
      </v-btn>
      <v-btn v-if="canEdit" color="primary" variant="flat" :prepend-icon="mdiPlus" @click="openAdd">
        Add a version
      </v-btn>
    </div>

    <v-sheet border rounded="lg" class="pa-3">
      <h2 class="text-subtitle-1 mb-2">
        {{
          compareWith === null
            ? "Text"
            : `Changes from ${compareWith === 0 ? "the built-in prompt" : `version ${String(compareWith)}`}`
        }}
      </h2>
      <pre v-if="compareWith === null" class="bs-prompt" aria-label="Prompt text">{{ text }}</pre>
      <pre v-else class="bs-prompt" aria-label="Prompt changes"><span
        v-for="(line, at) in diff"
        :key="at"
        :class="`bs-${line.kind}`"
      >{{ line.kind === "added" ? "+ " : line.kind === "removed" ? "- " : "  " }}{{ line.text }}
</span></pre>
    </v-sheet>

    <FormDialog
      v-model="adding"
      title="Add a version"
      submit-label="Add the version"
      :busy="busy"
      :error="addFailure"
      :submit-disabled="tooShort || tooLong"
      :width="760"
      @submit="add"
    >
      <v-textarea
        v-model="newBody"
        label="Prompt text"
        rows="14"
        auto-grow
        :counter="maxPrompt"
        :error-messages="tooLong ? [`At most ${maxPrompt} characters.`] : []"
      />
      <v-text-field v-model="newNote" label="What changed" maxlength="200" />
      <v-checkbox v-model="newUse" label="Use it for new missions" hide-details />
    </FormDialog>
  </section>
</template>

<style scoped>
.bs-compare {
  max-width: 26rem;
  min-width: min(14rem, 100%);
}
.bs-prompt {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.bs-added {
  background: rgb(var(--v-theme-success), 0.18);
}
.bs-removed {
  background: rgb(var(--v-theme-error), 0.18);
}
</style>

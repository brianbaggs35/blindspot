<script setup lang="ts">
import { mdiContentCopy, mdiDownload } from "@mdi/js";
import { computed, onMounted, ref } from "vue";
import { api, describe } from "../../api/client";
import type { RawOutput } from "../../api/types";
import { downloadText } from "../../download";
import { commandLine, duration, highlight, rawFileName } from "../../results";

// What the tool printed, as it printed it, with the command exactly as it ran, how it ended and
// how long it took.
const props = defineProps<{
  pentestId: string;
  resultId: string;
  title: string;
  tool: string | null;
}>();

const raw = ref<RawOutput | null>(null);
const output = ref("");
const failure = ref("");
const query = ref("");
const copied = ref(false);

// The page shows this panel only for the result it was given and builds it again for another, so
// nothing here can be answered late.
async function load() {
  try {
    const found = await api<RawOutput>(
      "GET",
      `/api/pentests/${props.pentestId}/results/${props.resultId}/raw`,
    );
    output.value = found.output;
    raw.value = found;
  } catch (error) {
    failure.value = describe(error);
  }
}

const shown = computed(() => highlight(output.value, query.value));

async function copy(output: string) {
  await navigator.clipboard.writeText(output);
  copied.value = true;
}

function download(output: string) {
  downloadText(rawFileName({ title: props.title, tool_id: props.tool }), output);
}

onMounted(load);
</script>

<template>
  <section aria-label="Raw view">
    <v-alert v-if="failure" type="error" variant="tonal" role="alert">
      Could not load the output: {{ failure }}
    </v-alert>
    <v-skeleton-loader v-else-if="raw === null" type="paragraph" />
    <template v-else>
      <v-card border class="mb-4">
        <v-card-text>
          <p class="text-body-2 mb-1">Command, as it ran</p>
          <code v-if="raw.command.length > 0" class="bs-command">{{
            commandLine(raw.command)
          }}</code>
          <p v-else class="text-body-2 text-medium-emphasis">
            No command: this result was written or imported, not run by the app.
          </p>
          <p class="text-body-2 mt-3">
            Exit code: {{ raw.exit_code ?? "—" }} · Took: {{ duration(raw.duration_ms) }}
          </p>
        </v-card-text>
      </v-card>

      <div class="d-flex flex-wrap align-center ga-2 mb-2">
        <v-text-field
          v-model="query"
          label="Search the output"
          hide-details
          clearable
          density="comfortable"
          class="bs-search"
        />
        <output v-if="query.trim() !== ''" class="text-body-2" aria-label="Matches">
          {{ shown.matches }} {{ shown.matches === 1 ? "match" : "matches" }}
        </output>
        <v-spacer />
        <v-btn variant="tonal" :prepend-icon="mdiContentCopy" @click="copy(raw.output)">
          {{ copied ? "Copied" : "Copy" }}
        </v-btn>
        <v-btn variant="tonal" :prepend-icon="mdiDownload" @click="download(raw.output)"
          >Download</v-btn
        >
      </div>

      <v-alert v-if="raw.truncated" type="warning" variant="tonal" class="mb-2">
        The output is {{ raw.size }} characters long. Only the first part is kept here.
      </v-alert>
      <pre class="bs-raw" tabindex="0" aria-label="Raw output"><template
        v-for="(line, row) in shown.lines"
        :key="row"
      ><template v-for="(token, at) in line" :key="at"><mark v-if="token.kind === 'match'">{{ token.text }}</mark><span v-else :class="`bs-${token.kind}`">{{ token.text }}</span></template>
</template></pre>
      <p v-if="shown.hiddenLines > 0" class="text-body-2 mt-2">
        {{ shown.hiddenLines }} more lines are not shown. Copy or download to get all of it.
      </p>
    </template>
  </section>
</template>

<style scoped>
.bs-command,
.bs-raw {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
}
.bs-command {
  overflow-wrap: anywhere;
}
.bs-raw {
  border: 1px solid rgb(var(--v-theme-on-surface), 0.2);
  border-radius: 6px;
  max-height: 32rem;
  overflow: auto;
  padding: 0.75rem;
  white-space: pre;
}
.bs-search {
  max-width: 22rem;
  min-width: min(14rem, 100%);
}
.bs-tag {
  color: rgb(var(--v-theme-primary));
}
.bs-key {
  color: rgb(var(--v-theme-secondary));
}
.bs-string {
  color: rgb(var(--v-theme-success));
}
.bs-number {
  color: rgb(var(--v-theme-warning));
}
</style>

<script setup lang="ts">
import type { ToolTestResult } from "../../api/types";

// What the version check of a tool really did: the command, how it ended, how long it took and
// what it printed.
defineProps<{ name: string; result: ToolTestResult | null; failure: string; busy: boolean }>();
const open = defineModel<boolean>({ required: true });
</script>

<template>
  <v-dialog v-model="open" max-width="640" :aria-label="`Test ${name}`">
    <v-card :title="`Test ${name}`">
      <v-card-text>
        <v-progress-linear v-if="busy" indeterminate aria-label="Running the version check" />
        <v-alert v-if="failure" type="error" variant="tonal" role="alert">{{ failure }}</v-alert>
        <template v-if="result">
          <v-alert v-if="result.timed_out" type="warning" variant="tonal" class="mb-3" role="alert">
            It did not finish in time and was stopped.
          </v-alert>
          <dl class="bs-facts">
            <dt>Ran</dt>
            <dd>{{ result.mode === "local" ? "Local" : "Docker" }}</dd>
            <dt>Command</dt>
            <dd>
              <code>{{ result.command.join(" ") }}</code>
            </dd>
            <dt>Ended with</dt>
            <dd>
              {{ result.exit_code === null ? "no exit code" : `exit code ${result.exit_code}` }}
            </dd>
            <dt>Took</dt>
            <dd>{{ result.duration_ms }} ms</dd>
            <dt>Version</dt>
            <dd>{{ result.version ?? "not found in the output" }}</dd>
          </dl>
          <h2 class="text-subtitle-1 mt-3 mb-1">Output</h2>
          <pre class="bs-output">{{ result.output === "" ? "(nothing)" : result.output }}</pre>
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="open = false">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
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
.bs-output {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
  max-height: 16rem;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>

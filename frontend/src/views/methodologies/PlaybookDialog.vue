<script setup lang="ts">
import { ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { Playbook, TestDetail } from "../../api/types";
import { joinLines, lines } from "../../methodologies";

// Replaces a test's playbook. Lists are typed one per line.
const props = defineProps<{ methodologyId: string; testId: string; playbook: Playbook }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ saved: [TestDetail] }>();

const summary = ref("");
const instructions = ref("");
const tools = ref<string[]>([]);
const manualReview = ref(false);
const safeSteps = ref("");
const activeSteps = ref("");
const intrusiveSteps = ref("");
const evidence = ref("");
const success = ref("");
const failureText = ref("");
const notApplicable = ref("");
const busy = ref(false);
const failure = ref("");

watch(open, (isOpen) => {
  if (!isOpen) return;
  const from = props.playbook;
  failure.value = "";
  summary.value = from.summary;
  instructions.value = from.instructions;
  tools.value = [...from.tools];
  manualReview.value = from.manual_review;
  safeSteps.value = joinLines(from.safe_steps);
  activeSteps.value = joinLines(from.active_steps);
  intrusiveSteps.value = joinLines(from.intrusive_steps);
  evidence.value = joinLines(from.evidence);
  success.value = from.success;
  failureText.value = from.failure;
  notApplicable.value = joinLines(from.not_applicable);
});

async function save() {
  busy.value = true;
  failure.value = "";
  const body: Playbook = {
    summary: summary.value.trim(),
    instructions: instructions.value.trim(),
    tools: tools.value,
    manual_review: manualReview.value,
    safe_steps: lines(safeSteps.value),
    active_steps: lines(activeSteps.value),
    intrusive_steps: lines(intrusiveSteps.value),
    evidence: lines(evidence.value),
    success: success.value.trim(),
    failure: failureText.value.trim(),
    not_applicable: lines(notApplicable.value),
  };
  try {
    const saved = await api<TestDetail>(
      "PUT",
      `/api/methodologies/${props.methodologyId}/tests/${props.testId}/playbook`,
      body,
    );
    open.value = false;
    emit("saved", saved);
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="760" scrollable :persistent="busy">
    <v-card title="Edit the playbook">
      <v-form @submit.prevent="save">
        <v-card-text>
          <v-alert v-if="failure" type="error" variant="tonal" class="mb-4" role="alert">
            {{ failure }}
          </v-alert>
          <p class="text-body-2 mb-4">
            This replaces what the test's agent is told to do. The original stays and comes back if
            you put it back. Lists take one entry per line.
          </p>
          <v-text-field v-model="summary" label="Summary" counter="600" />
          <v-textarea v-model="instructions" label="Instructions to the agent" auto-grow rows="6" />
          <v-combobox
            v-model="tools"
            label="Tools"
            multiple
            chips
            closable-chips
            hint="Tool ids such as b.http or c.nmap"
            persistent-hint
            class="mb-4"
          />
          <v-switch
            v-model="manualReview"
            label="A person should review the result"
            color="primary"
            hide-details
          />
          <v-textarea v-model="safeSteps" label="Safe steps" auto-grow rows="2" />
          <v-textarea v-model="activeSteps" label="Active steps" auto-grow rows="2" />
          <v-textarea
            v-model="intrusiveSteps"
            label="Intrusive steps (always ask first)"
            auto-grow
            rows="2"
          />
          <v-textarea v-model="evidence" label="Evidence to bring back" auto-grow rows="2" />
          <v-textarea v-model="success" label="Mark it passed when" auto-grow rows="2" />
          <v-textarea v-model="failureText" label="Report a finding when" auto-grow rows="2" />
          <v-textarea
            v-model="notApplicable"
            label="Mark it not applicable when"
            auto-grow
            rows="2"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn :disabled="busy" @click="open = false">Cancel</v-btn>
          <v-btn type="submit" color="primary" variant="flat" :loading="busy">Save playbook</v-btn>
        </v-card-actions>
      </v-form>
    </v-card>
  </v-dialog>
</template>

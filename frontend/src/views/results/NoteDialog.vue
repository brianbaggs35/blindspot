<script setup lang="ts">
import { ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { PentestResultFull, Severity } from "../../api/types";
import FormDialog from "../../components/FormDialog.vue";
import { SEVERITY_CHOICES } from "../../results";

// A result written by hand: what a person saw or tried that no tool recorded.
const props = defineProps<{ pentestId: string }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ added: [result: PentestResultFull] }>();

const title = ref("");
const notes = ref("");
const severity = ref<Severity | null>(null);
const tags = ref<string[]>([]);
const testId = ref("");
const busy = ref(false);
const failure = ref("");

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    title.value = "";
    notes.value = "";
    severity.value = null;
    tags.value = [];
    testId.value = "";
    failure.value = "";
  },
  { immediate: true },
);

async function submit() {
  busy.value = true;
  failure.value = "";
  try {
    const made = await api<PentestResultFull>("POST", `/api/pentests/${props.pentestId}/results`, {
      title: title.value,
      notes: notes.value,
      severity: severity.value,
      tags: tags.value,
      test_id: testId.value.trim() === "" ? null : testId.value.trim(),
    });
    open.value = false;
    emit("added", made);
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <FormDialog
    v-model="open"
    title="Write a result by hand"
    submit-label="Add result"
    :busy="busy"
    :error="failure"
    :width="560"
    @submit="submit"
  >
    <v-text-field v-model="title" label="Title" counter="200" autocomplete="off" />
    <v-textarea v-model="notes" label="What you saw or tried" auto-grow rows="3" class="mt-4" />
    <v-select
      v-model="severity"
      :items="SEVERITY_CHOICES"
      label="How serious (optional)"
      clearable
      class="mt-4"
    />
    <v-text-field v-model="testId" label="Checklist test (optional)" class="mt-4" />
    <v-combobox
      v-model="tags"
      label="Tags (optional)"
      multiple
      chips
      closable-chips
      hint="Lower case letters, numbers, spaces, dashes. Press Enter after each."
      persistent-hint
      class="mt-4"
    />
  </FormDialog>
</template>

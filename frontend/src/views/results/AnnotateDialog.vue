<script setup lang="ts">
import { ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { PentestResultFull } from "../../api/types";
import FormDialog from "../../components/FormDialog.vue";

// What a person adds to a result: a title of their own, notes, tags and the checklist test it
// belongs to. The output itself cannot be changed.
const props = defineProps<{ pentestId: string; result: PentestResultFull }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ saved: [result: PentestResultFull] }>();

const title = ref("");
const notes = ref("");
const tags = ref<string[]>([]);
const testId = ref("");
const busy = ref(false);
const failure = ref("");

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    title.value = props.result.title;
    notes.value = props.result.notes;
    tags.value = [...props.result.tags];
    testId.value = props.result.test_id ?? "";
    failure.value = "";
  },
  { immediate: true },
);

async function submit() {
  busy.value = true;
  failure.value = "";
  try {
    const saved = await api<PentestResultFull>(
      "PATCH",
      `/api/pentests/${props.pentestId}/results/${props.result.id}`,
      {
        title: title.value,
        notes: notes.value,
        tags: tags.value,
        test_id: testId.value.trim() === "" ? null : testId.value.trim(),
      },
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
  <FormDialog
    v-model="open"
    title="Edit notes and tags"
    submit-label="Save"
    :busy="busy"
    :error="failure"
    :width="560"
    @submit="submit"
  >
    <v-text-field v-model="title" label="Title" counter="200" autocomplete="off" />
    <v-textarea v-model="notes" label="Notes" auto-grow rows="3" class="mt-4" />
    <v-text-field v-model="testId" label="Checklist test (optional)" class="mt-4" />
    <v-combobox
      v-model="tags"
      label="Tags"
      multiple
      chips
      closable-chips
      hint="Lower case letters, numbers, spaces, dashes. Press Enter after each."
      persistent-hint
      class="mt-4"
    />
  </FormDialog>
</template>

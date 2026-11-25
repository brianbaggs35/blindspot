<script setup lang="ts">
import { ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { PentestResultFull } from "../../api/types";
import FormDialog from "../../components/FormDialog.vue";
import { IMPORT_PARSERS } from "../../results";

// Output from a tool that ran somewhere else, pasted or loaded from a file. The server reads it
// the way it reads the output of a run, and says so when it cannot.
const props = defineProps<{ pentestId: string }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ added: [result: PentestResultFull] }>();

const parser = ref("nmap_xml");
const content = ref("");
const title = ref("");
const busy = ref(false);
const failure = ref("");

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    parser.value = "nmap_xml";
    content.value = "";
    title.value = "";
    failure.value = "";
  },
  { immediate: true },
);

async function load(files: File | File[] | null | undefined) {
  const file = Array.isArray(files) ? files[0] : files;
  if (file) content.value = await file.text();
}

async function submit() {
  busy.value = true;
  failure.value = "";
  try {
    const made = await api<PentestResultFull>(
      "POST",
      `/api/pentests/${props.pentestId}/results/import`,
      {
        parser: parser.value,
        content: content.value,
        ...(title.value.trim() === "" ? {} : { title: title.value.trim() }),
      },
    );
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
    title="Import tool output"
    submit-label="Import"
    :busy="busy"
    :error="failure"
    :width="640"
    @submit="submit"
  >
    <v-select v-model="parser" :items="IMPORT_PARSERS" label="Which tool made it" />
    <v-file-input
      label="Load from a file (optional)"
      class="mt-4"
      density="comfortable"
      @update:model-value="load"
    />
    <v-textarea
      v-model="content"
      label="Output"
      hint="Paste the output here, or load a file above."
      persistent-hint
      rows="6"
      class="mt-4 bs-mono"
    />
    <v-text-field v-model="title" label="Title (optional)" class="mt-4" autocomplete="off" />
  </FormDialog>
</template>

<style scoped>
.bs-mono :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
}
</style>

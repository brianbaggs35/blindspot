<script setup lang="ts">
import { ref, watch } from "vue";
import { api, describe } from "../../api/client";
import FormDialog from "../../components/FormDialog.vue";

// Findings from a Blindspot export (JSON) or from a scanner's SARIF report. Ones already here
// (the same title and target) are skipped, and the answer says how many were.
const props = defineProps<{ pentestId: string }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ imported: [message: string] }>();

const format = ref<"json" | "sarif">("json");
const content = ref("");
const busy = ref(false);
const failure = ref("");

watch(open, (now) => {
  if (!now) return;
  format.value = "json";
  content.value = "";
  failure.value = "";
});

async function load(files: File | File[] | null | undefined) {
  const file = Array.isArray(files) ? files[0] : files;
  if (!file) return;
  content.value = await file.text();
  if (file.name.endsWith(".sarif")) format.value = "sarif";
}

async function submit() {
  busy.value = true;
  failure.value = "";
  try {
    const done = await api<{ created: number; skipped: number }>(
      "POST",
      `/api/pentests/${props.pentestId}/findings/import`,
      { format: format.value, content: content.value },
    );
    open.value = false;
    emit(
      "imported",
      `${String(done.created)} imported${done.skipped > 0 ? `, ${String(done.skipped)} skipped` : ""}.`,
    );
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
    title="Import findings"
    submit-label="Import"
    :busy="busy"
    :error="failure"
    :submit-disabled="content.trim() === ''"
    :width="640"
    @submit="submit"
  >
    <v-select
      v-model="format"
      :items="[
        { value: 'json', title: 'A Blindspot export (JSON)' },
        { value: 'sarif', title: 'A scanner report (SARIF)' },
      ]"
      label="What the file is"
    />
    <v-file-input
      label="Load from a file (optional)"
      class="mt-4"
      density="comfortable"
      @update:model-value="load"
    />
    <v-textarea
      v-model="content"
      label="Contents"
      hint="Paste the file here, or load it above."
      persistent-hint
      rows="6"
      class="mt-4"
    />
  </FormDialog>
</template>

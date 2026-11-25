<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { EvidenceKind, ResultList } from "../../api/types";
import FormDialog from "../../components/FormDialog.vue";
import { EVIDENCE_KINDS } from "../../findings";

// Add evidence to a finding. Anything that looks like a secret is sealed unless it is said not
// to be; a sealed piece is shown masked everywhere until an administrator reveals it.
const props = defineProps<{ pentestId: string; findingId: string }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ added: [] }>();

const MAX_IMAGE = 2 * 1024 * 1024;

const kind = ref<EvidenceKind>("note");
const title = ref("");
const body = ref("");
const mime = ref<string | null>(null);
const sealed = ref<boolean | null>(null);
const resultId = ref<string | null>(null);
const results = ref<{ value: string; title: string }[]>([]);
const busy = ref(false);
const failure = ref("");

watch(open, async (now) => {
  if (!now) return;
  kind.value = "note";
  title.value = "";
  body.value = "";
  mime.value = null;
  sealed.value = null;
  resultId.value = null;
  failure.value = "";
  try {
    const list = await api<ResultList>("GET", `/api/pentests/${props.pentestId}/results?limit=200`);
    results.value = list.items.map((one) => ({ value: one.id, title: one.title }));
  } catch (error) {
    failure.value = describe(error);
  }
});

async function picture(files: File | File[] | null | undefined) {
  const file = Array.isArray(files) ? files[0] : files;
  body.value = "";
  mime.value = null;
  if (!file) return;
  if (file.size > MAX_IMAGE) {
    failure.value = "A screenshot may be 2 MB at most.";
    return;
  }
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (const byte of bytes) binary += String.fromCodePoint(byte);
  body.value = btoa(binary);
  mime.value = file.type;
  if (title.value === "") title.value = file.name;
}

const ready = computed(
  () =>
    title.value.trim() !== "" &&
    (kind.value === "result" ? resultId.value !== null : body.value !== ""),
);

async function submit() {
  busy.value = true;
  failure.value = "";
  const content =
    kind.value === "result"
      ? { result_id: resultId.value }
      : { body: body.value, ...(kind.value === "screenshot" ? { mime: mime.value } : {}) };
  try {
    await api("POST", `/api/pentests/${props.pentestId}/findings/${props.findingId}/evidence`, {
      kind: kind.value,
      title: title.value.trim(),
      sealed: sealed.value,
      ...content,
    });
    open.value = false;
    emit("added");
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
    title="Add evidence"
    submit-label="Add"
    :busy="busy"
    :error="failure"
    :submit-disabled="!ready"
    :width="640"
    @submit="submit"
  >
    <v-select v-model="kind" :items="EVIDENCE_KINDS" label="What it is" />
    <v-text-field v-model="title" label="Title" maxlength="200" class="mt-3" />
    <v-select
      v-if="kind === 'result'"
      v-model="resultId"
      :items="results"
      label="Which result"
      class="mt-3"
    />
    <v-file-input
      v-else-if="kind === 'screenshot'"
      label="Screenshot (PNG, JPEG or WebP, 2 MB at most)"
      accept="image/png,image/jpeg,image/webp"
      class="mt-3"
      @update:model-value="picture"
    />
    <v-textarea
      v-else
      v-model="body"
      :label="kind === 'note' ? 'Note' : 'The request and the response'"
      rows="6"
      class="mt-3 bs-mono"
    />
    <v-checkbox
      v-if="kind !== 'result'"
      :model-value="sealed === true"
      label="Seal it: hide it in lists and exports"
      hide-details
      @update:model-value="sealed = $event === true ? true : null"
    />
  </FormDialog>
</template>

<style scoped>
.bs-mono :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
}
</style>

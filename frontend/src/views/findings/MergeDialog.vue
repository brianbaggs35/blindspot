<script setup lang="ts">
import { ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { Finding, FindingSummary } from "../../api/types";
import FormDialog from "../../components/FormDialog.vue";
import { label } from "../../findings";

// Fold a finding into another that it repeats: the evidence moves over and this one goes to the
// trash, pointing at the one that was kept.
const props = defineProps<{ pentestId: string; finding: Finding }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ merged: [kept: Finding] }>();

const choices = ref<{ value: string; title: string }[]>([]);
const into = ref<string | null>(null);
const busy = ref(false);
const failure = ref("");

watch(open, async (now) => {
  if (!now) return;
  into.value = props.finding.duplicates[0]?.id ?? null;
  failure.value = "";
  try {
    const list = await api<{ items: FindingSummary[] }>(
      "GET",
      `/api/pentests/${props.pentestId}/findings?limit=200&sort=number&order=asc`,
    );
    choices.value = list.items
      .filter((one) => one.id !== props.finding.id)
      .map((one) => ({ value: one.id, title: `${label(one.number)} ${one.title}` }));
  } catch (error) {
    failure.value = describe(error);
  }
});

async function submit() {
  busy.value = true;
  failure.value = "";
  try {
    const kept = await api<Finding>(
      "POST",
      `/api/pentests/${props.pentestId}/findings/${props.finding.id}/merge`,
      { into: into.value },
    );
    open.value = false;
    emit("merged", kept);
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
    :title="`Merge ${label(finding.number)} into another finding`"
    submit-label="Merge"
    :busy="busy"
    :error="failure"
    :submit-disabled="into === null"
    danger
    :width="560"
    @submit="submit"
  >
    <p class="text-body-2 mb-4">
      The evidence, tests, CWEs and references of this finding move to the one you pick, and this
      one goes to the trash.
    </p>
    <v-select v-model="into" :items="choices" label="Keep this finding" />
  </FormDialog>
</template>

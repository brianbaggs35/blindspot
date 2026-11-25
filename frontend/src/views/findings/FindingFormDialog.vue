<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { Finding, FindingDraft, FindingsReference, Severity } from "../../api/types";
import FormDialog from "../../components/FormDialog.vue";
import { SEVERITY_CHOICES } from "../../results";
import { CONFIDENCE_CHOICES, draftOf, emptyDraft, words } from "../../findings";
import CvssCalculator from "./CvssCalculator.vue";

// Write a finding, or change one. The severity can be left to the CVSS vector.
const props = defineProps<{ pentestId: string; finding?: Finding | undefined }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ saved: [finding: Finding] }>();

const draft = ref<FindingDraft>(emptyDraft());
const cweText = ref("");
const testText = ref("");
const referenceText = ref("");
const owasp = ref<Record<string, string>>({});
const busy = ref(false);
const failure = ref("");
const tab = ref<"4.0" | "3.1">("4.0");

watch(open, async (now) => {
  if (!now) return;
  draft.value = props.finding ? draftOf(props.finding) : emptyDraft();
  cweText.value = draft.value.cwe.join(" ");
  testText.value = draft.value.test_ids.join(" ");
  referenceText.value = draft.value.references.join("\n");
  failure.value = "";
  tab.value = "4.0";
  if (Object.keys(owasp.value).length === 0) {
    try {
      owasp.value = (await api<FindingsReference>("GET", "/api/findings/reference")).owasp;
    } catch (error) {
      failure.value = describe(error);
    }
  }
});

const owaspChoices = computed(() =>
  Object.entries(owasp.value).map(([value, name]) => ({ value, title: `${value} ${name}` })),
);
const rated = computed(
  () =>
    draft.value.severity !== null ||
    draft.value.cvss4_vector !== null ||
    draft.value.cvss31_vector !== null,
);

async function save() {
  busy.value = true;
  failure.value = "";
  // A severity that was not touched is left out, so a new vector can re-rate the finding.
  const { severity, ...rest } = draft.value;
  const untouched = props.finding !== undefined && severity === props.finding.severity;
  const body = {
    ...rest,
    ...(untouched ? {} : { severity }),
    cwe: words(cweText.value.toUpperCase()),
    test_ids: words(testText.value),
    references: referenceText.value
      .split("\n")
      .map((one) => one.trim())
      .filter((one) => one !== ""),
  };
  try {
    const saved = props.finding
      ? await api<Finding>(
          "PATCH",
          `/api/pentests/${props.pentestId}/findings/${props.finding.id}`,
          body,
        )
      : await api<Finding>("POST", `/api/pentests/${props.pentestId}/findings`, body);
    open.value = false;
    emit("saved", saved);
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}

const setSeverity = (value: Severity | null) => (draft.value.severity = value);
</script>

<template>
  <FormDialog
    v-model="open"
    :title="finding ? 'Change the finding' : 'Write a finding'"
    :submit-label="finding ? 'Save' : 'Add the finding'"
    :busy="busy"
    :error="failure"
    :submit-disabled="draft.title.trim() === '' || !rated"
    :width="820"
    @submit="save"
  >
    <v-text-field v-model="draft.title" label="Title" maxlength="200" />
    <v-textarea v-model="draft.description" label="What is wrong" rows="3" auto-grow />
    <v-text-field v-model="draft.target" label="Affected target (a URL, host or path)" />
    <div class="bs-two">
      <v-text-field
        v-model="testText"
        label="Tests (WSTG-CONF-07 …)"
        hint="Separate with spaces."
        persistent-hint
      />
      <v-text-field
        v-model="cweText"
        label="CWE (CWE-79 …)"
        hint="Separate with spaces."
        persistent-hint
      />
    </div>
    <div class="bs-two mt-3">
      <v-select v-model="draft.owasp" :items="owaspChoices" label="OWASP Top 10" clearable />
      <v-select v-model="draft.confidence" :items="CONFIDENCE_CHOICES" label="Confidence" />
    </div>
    <h3 class="text-subtitle-1 mt-2 mb-2">Rating</h3>
    <v-tabs v-model="tab" density="compact" aria-label="CVSS version">
      <v-tab value="4.0">CVSS 4.0</v-tab>
      <v-tab value="3.1">CVSS 3.1</v-tab>
    </v-tabs>
    <div class="mt-3">
      <CvssCalculator v-if="tab === '4.0'" v-model="draft.cvss4_vector" version="4.0" />
      <CvssCalculator v-else v-model="draft.cvss31_vector" version="3.1" />
    </div>
    <v-select
      :model-value="draft.severity"
      :items="SEVERITY_CHOICES"
      label="Severity"
      clearable
      class="mt-3"
      hint="Leave it empty to take the severity from the CVSS vector."
      persistent-hint
      @update:model-value="setSeverity"
    />
    <v-textarea v-model="draft.remediation" label="How to fix it" rows="3" auto-grow class="mt-3" />
    <v-textarea
      v-model="referenceText"
      label="References (one web address on each line)"
      rows="2"
      auto-grow
    />
  </FormDialog>
</template>

<style scoped>
.bs-two {
  display: grid;
  gap: 0 0.75rem;
  grid-template-columns: repeat(auto-fit, minmax(min(16rem, 100%), 1fr));
}
</style>

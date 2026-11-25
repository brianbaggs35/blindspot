<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { ToolSetting } from "../../api/types";
import FormDialog from "../../components/FormDialog.vue";
import { MODE_CHOICES, type SettingDraft, bodyOf, draftOf, risksUpTo } from "../../tools";

// How one tool runs: on or off, Local or Docker, the program or image, and the limits. What is
// left empty is what the tool's own definition says (shown as a hint).
const props = defineProps<{ tool: ToolSetting }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ saved: [tool: ToolSetting] }>();

const draft = ref<SettingDraft>(draftOf(props.tool));
const busy = ref(false);
const failure = ref("");

watch(open, (now) => {
  if (!now) return;
  draft.value = draftOf(props.tool);
  failure.value = "";
});

const binaryHint = computed(
  () => `Empty means ${props.tool.default_binary ?? "the program the tool defines"}.`,
);
const builtin = computed(() => props.tool.execution === "builtin");
const showLocal = computed(() => !builtin.value && draft.value.mode !== "docker");
const showDocker = computed(() => !builtin.value && draft.value.mode !== "local");

async function save() {
  busy.value = true;
  failure.value = "";
  try {
    const saved = await api<ToolSetting>(
      "PUT",
      `/api/tools/settings/${props.tool.id}`,
      bodyOf(draft.value),
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
    :title="`Settings for ${tool.name}`"
    submit-label="Save"
    :busy="busy"
    :error="failure"
    :width="720"
    @submit="save"
  >
    <v-switch v-model="draft.enabled" label="This tool may be used" color="primary" hide-details />
    <v-select
      v-if="!builtin"
      v-model="draft.mode"
      :items="MODE_CHOICES"
      item-title="title"
      item-value="value"
      label="Where it runs"
      class="mt-3"
      hint="If it cannot run there it is not moved: you are told what is wrong."
      persistent-hint
    />
    <v-text-field
      v-if="showLocal"
      v-model="draft.binary_path"
      label="Program path (Local)"
      :hint="binaryHint"
      persistent-hint
      class="mt-3"
    />
    <v-text-field
      v-if="showDocker"
      v-model="draft.image"
      label="Image with its digest (Docker)"
      :hint="
        tool.default_image
          ? `Empty means ${tool.default_image}.`
          : 'A reference ending in @sha256: and 64 hex characters.'
      "
      persistent-hint
      class="mt-3"
    />
    <h2 class="text-subtitle-1 mt-4 mb-2">Limits</h2>
    <div class="bs-limits">
      <v-text-field
        v-model="draft.timeout_s"
        type="number"
        label="Timeout (seconds)"
        :hint="`Empty means ${tool.limits.timeout_s}.`"
        persistent-hint
      />
      <v-text-field
        v-model="draft.max_output_mb"
        type="number"
        label="Output cap (MB)"
        :hint="`Empty means ${tool.limits.max_output_mb}.`"
        persistent-hint
      />
      <v-text-field
        v-model="draft.rate_per_s"
        type="number"
        label="Requests per second, for each target"
        hint="Empty means no limit."
        persistent-hint
      />
      <v-text-field
        v-model="draft.cpus"
        type="number"
        label="CPUs (Docker only)"
        hint="Empty means no limit."
        persistent-hint
      />
      <v-text-field
        v-model="draft.memory_mb"
        type="number"
        label="Memory in MB (Docker only)"
        hint="Empty means no limit."
        persistent-hint
      />
      <v-select
        v-model="draft.max_risk"
        :items="risksUpTo(tool.risk)"
        item-title="title"
        item-value="value"
        label="Most it may do"
        clearable
        :hint="`Empty means ${tool.risk}, the tool's own class.`"
        persistent-hint
      />
    </div>
  </FormDialog>
</template>

<style scoped>
.bs-limits {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(auto-fit, minmax(min(15rem, 100%), 1fr));
}
</style>

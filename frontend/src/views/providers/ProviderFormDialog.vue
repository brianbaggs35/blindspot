<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { KindInfo, Provider, ProviderKind } from "../../api/types";
import FormDialog from "../../components/FormDialog.vue";
import { KIND_NOTES, priceOrNull } from "../../providers";

// Adds a provider, or changes one. A saved key is never shown again: the field starts empty, and
// leaving it empty keeps the key that is there.
const props = defineProps<{ provider: Provider | null; kinds: KindInfo[] }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ saved: [Provider] }>();

const kind = ref<ProviderKind>("anthropic");
const name = ref("");
const baseUrl = ref("");
const apiKey = ref("");
const removeKey = ref(false);
const enabled = ref(true);
const budget = ref("");
const hardStop = ref(false);
const busy = ref(false);
const failure = ref("");

const editing = computed(() => props.provider !== null);
const title = computed(() =>
  props.provider === null ? "Add an AI provider" : `Edit ${props.provider.name}`,
);
const info = computed(() => props.kinds.find((one) => one.kind === kind.value));
const kindItems = computed(() => props.kinds.map((one) => ({ title: one.label, value: one.kind })));
const needsKey = computed(() => info.value?.needs_key === true);
const defaultAddress = () => (info.value === undefined ? "" : info.value.default_base_url);
const keyHint = computed(() => {
  const saved = props.provider;
  if (saved === null)
    return needsKey.value ? "Stored encrypted. It is never shown again." : "Optional.";
  return saved.key_last4 === null
    ? "No key is saved."
    : `A key ending in ${saved.key_last4} is saved. Leave this empty to keep it.`;
});

// Each time the dialog opens it starts from the provider (or from the first kind).
watch(open, (isOpen) => {
  if (!isOpen) return;
  failure.value = "";
  apiKey.value = "";
  removeKey.value = false;
  kind.value = props.provider?.kind ?? "anthropic";
  name.value = props.provider?.name ?? "";
  baseUrl.value = props.provider?.base_url ?? defaultAddress();
  enabled.value = props.provider?.enabled ?? true;
  budget.value = props.provider?.monthly_budget_usd ?? "";
  hardStop.value = props.provider?.hard_stop ?? false;
});

// A new provider starts from the address its kind usually has.
watch(kind, () => {
  if (!editing.value) baseUrl.value = defaultAddress();
});

function body() {
  const common = {
    name: name.value,
    base_url: baseUrl.value,
    enabled: enabled.value,
    monthly_budget_usd: priceOrNull(budget.value),
    hard_stop: hardStop.value,
  };
  const key = apiKey.value.trim() === "" ? {} : { api_key: apiKey.value };
  return editing.value
    ? { ...common, ...key, ...(removeKey.value ? { remove_key: true } : {}) }
    : { ...common, kind: kind.value, ...key };
}

async function submit() {
  failure.value = "";
  busy.value = true;
  try {
    const saved =
      props.provider === null
        ? await api<Provider>("POST", "/api/providers", body())
        : await api<Provider>("PATCH", `/api/providers/${props.provider.id}`, body());
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
    :title="title"
    :submit-label="editing ? 'Save' : 'Add provider'"
    :busy="busy"
    :error="failure"
    @submit="submit"
  >
    <v-select
      v-model="kind"
      :items="kindItems"
      label="Kind"
      :disabled="editing"
      :hint="editing ? 'The kind cannot be changed.' : ''"
      :persistent-hint="editing"
      class="mb-2"
    />
    <p class="text-body-2 text-medium-emphasis mb-4">{{ KIND_NOTES[kind] }}</p>
    <v-text-field v-model="name" label="Name" autocomplete="off" required class="mb-2" />
    <v-text-field
      v-model="baseUrl"
      label="Address"
      autocomplete="off"
      hint="Where the provider's API is. The usual address is filled in."
      persistent-hint
      class="mb-2"
    />
    <v-text-field
      v-model="apiKey"
      label="API key"
      type="password"
      autocomplete="off"
      :hint="keyHint"
      persistent-hint
      class="mb-2"
    />
    <v-checkbox
      v-if="editing && provider?.has_key && !needsKey"
      v-model="removeKey"
      label="Remove the saved key"
      density="compact"
      hide-details
    />
    <v-text-field
      v-model="budget"
      label="Monthly budget (USD)"
      inputmode="decimal"
      autocomplete="off"
      hint="Optional. The month starts on the 1st, in UTC."
      persistent-hint
      class="mb-2"
    />
    <v-switch
      v-model="hardStop"
      label="Stop calls when the budget is used up"
      color="primary"
      density="compact"
      inset
      hide-details
    />
    <v-switch
      v-model="enabled"
      label="Use this provider"
      color="primary"
      density="compact"
      inset
      hide-details
    />
  </FormDialog>
</template>

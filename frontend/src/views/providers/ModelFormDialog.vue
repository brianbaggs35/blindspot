<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { Price, ProviderModel } from "../../api/types";
import FormDialog from "../../components/FormDialog.vue";
import { CAPABILITIES, priceOrNull, wholeOrNull } from "../../providers";

// Adds a model by hand, or changes one. Prices are what an administrator sets over the catalog's;
// a field left empty uses the catalog's price.
const props = defineProps<{ providerId: string; model: ProviderModel | null }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ saved: [ProviderModel] }>();

const PRICE_FIELDS = [
  { key: "input", label: "Input" },
  { key: "output", label: "Output" },
  { key: "cache_read", label: "Cache read" },
  { key: "cache_write", label: "Cache write" },
  { key: "cache_write_long", label: "Cache write, long" },
] as const;

const modelId = ref("");
const displayName = ref("");
const contextTokens = ref("");
const maxOutput = ref("");
const capabilities = ref<string[]>([]);
const enabled = ref(true);
const prices = ref<Record<keyof Price, string>>(emptyPrices());
const busy = ref(false);
const failure = ref("");

const editing = computed(() => props.model !== null);
const title = computed(() =>
  props.model === null ? "Add a model" : `Edit ${props.model.display_name}`,
);

function emptyPrices(): Record<keyof Price, string> {
  return { input: "", output: "", cache_read: "", cache_write: "", cache_write_long: "" };
}

watch(open, (isOpen) => {
  if (!isOpen) return;
  failure.value = "";
  modelId.value = props.model?.model_id ?? "";
  displayName.value = props.model?.display_name ?? "";
  contextTokens.value = "";
  maxOutput.value = "";
  capabilities.value = props.model ? [...props.model.capabilities] : [];
  enabled.value = props.model?.enabled ?? true;
  const set = props.model?.overrides;
  prices.value = {
    input: set?.input ?? "",
    output: set?.output ?? "",
    cache_read: set?.cache_read ?? "",
    cache_write: set?.cache_write ?? "",
    cache_write_long: set?.cache_write_long ?? "",
  };
});

function priceBody() {
  const sent = prices.value;
  return {
    price_input: priceOrNull(sent.input),
    price_output: priceOrNull(sent.output),
    price_cache_read: priceOrNull(sent.cache_read),
    price_cache_write: priceOrNull(sent.cache_write),
    price_cache_write_long: priceOrNull(sent.cache_write_long),
  };
}

async function submit() {
  failure.value = "";
  busy.value = true;
  try {
    const base = `/api/providers/${props.providerId}/models`;
    const saved =
      props.model === null
        ? await api<ProviderModel>("POST", base, {
            model_id: modelId.value,
            display_name: displayName.value,
            context_tokens: wholeOrNull(contextTokens.value),
            max_output_tokens: wholeOrNull(maxOutput.value),
            // Empty means "whatever the catalog says for this model".
            capabilities: capabilities.value.length === 0 ? null : capabilities.value,
            enabled: enabled.value,
            ...priceBody(),
          })
        : await api<ProviderModel>("PATCH", `${base}/${props.model.id}`, {
            display_name: displayName.value,
            capabilities: capabilities.value,
            enabled: enabled.value,
            ...priceBody(),
          });
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
    :submit-label="editing ? 'Save' : 'Add model'"
    :busy="busy"
    :error="failure"
    @submit="submit"
  >
    <v-text-field
      v-if="!editing"
      v-model="modelId"
      label="Model id"
      autocomplete="off"
      hint="Exactly as the provider names it, such as claude-sonnet-5-5."
      persistent-hint
      class="mb-2"
    />
    <v-text-field
      v-model="displayName"
      label="Name"
      autocomplete="off"
      hint="Shown in the app. Optional when the catalog knows the model."
      persistent-hint
      class="mb-2"
    />
    <v-row v-if="!editing" dense>
      <v-col cols="12" sm="6">
        <v-text-field
          v-model="contextTokens"
          label="Context size (tokens)"
          inputmode="numeric"
          autocomplete="off"
        />
      </v-col>
      <v-col cols="12" sm="6">
        <v-text-field
          v-model="maxOutput"
          label="Largest answer (tokens)"
          inputmode="numeric"
          autocomplete="off"
        />
      </v-col>
    </v-row>
    <v-select
      v-model="capabilities"
      :items="CAPABILITIES"
      label="Capabilities"
      multiple
      chips
      :hint="editing ? '' : 'Leave empty to use the catalog.'"
      :persistent-hint="!editing"
      class="mb-2"
    />
    <fieldset class="bs-fieldset mb-2">
      <legend class="text-subtitle-2">Your prices (USD per million tokens)</legend>
      <p class="text-body-2 text-medium-emphasis mb-3">
        Leave a price empty to use the catalog's. Cache prices only matter for providers that charge
        for caching.
      </p>
      <v-row dense>
        <v-col v-for="field in PRICE_FIELDS" :key="field.key" cols="12" sm="6">
          <v-text-field
            v-model="prices[field.key]"
            :label="field.label"
            inputmode="decimal"
            autocomplete="off"
            density="compact"
          />
        </v-col>
      </v-row>
    </fieldset>
    <v-switch
      v-model="enabled"
      label="Use this model"
      color="primary"
      density="compact"
      inset
      hide-details
    />
  </FormDialog>
</template>

<style scoped>
.bs-fieldset {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 12px 16px 4px;
}
</style>

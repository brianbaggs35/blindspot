<script setup lang="ts">
import { computed, ref } from "vue";
import { api, describe } from "../../api/client";
import type { Provider, ProviderModel, RoleDefault } from "../../api/types";

// The model each job uses unless a pentest says otherwise. A change is saved the moment it is
// made.
const props = defineProps<{
  roles: RoleDefault[];
  providers: Provider[];
  models: ProviderModel[];
  canEdit: boolean;
}>();
const emit = defineEmits<{ changed: [string] }>();

const failure = ref("");
const busyRole = ref("");

// Only models that are on, on providers that are on, can be chosen.
const items = computed(() => {
  const live = new Map(props.providers.filter((one) => one.enabled).map((one) => [one.id, one]));
  return props.models.flatMap((model) => {
    const provider = live.get(model.provider_id);
    return provider && model.enabled
      ? [{ title: `${provider.name} · ${model.display_name}`, value: model.id }]
      : [];
  });
});

async function choose(role: RoleDefault, value: string | null) {
  failure.value = "";
  busyRole.value = role.role;
  try {
    if (value === null) await api("DELETE", `/api/ai/role-defaults/${role.role}`);
    else await api("PUT", `/api/ai/role-defaults/${role.role}`, { model_ref: value });
    emit("changed", role.label.replace(/:.*/, ""));
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busyRole.value = "";
  }
}
</script>

<template>
  <section aria-labelledby="role-defaults-title">
    <h2 id="role-defaults-title" class="text-h6 mb-1">Default model for each job</h2>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Agents that have no model of their own use the one chosen here.
    </p>
    <v-alert v-if="failure" type="error" variant="tonal" class="mb-4">{{ failure }}</v-alert>
    <v-card border>
      <v-card-text>
        <v-select
          v-for="role in roles"
          :key="role.role"
          :model-value="role.model_ref"
          :items="items"
          :label="role.label"
          :disabled="!canEdit"
          :loading="busyRole === role.role"
          clearable
          no-data-text="Add and turn on a model first."
          @update:model-value="(value: string | null) => choose(role, value)"
        />
      </v-card-text>
    </v-card>
  </section>
</template>

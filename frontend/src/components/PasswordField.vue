<script setup lang="ts">
import { mdiEye, mdiEyeOff } from "@mdi/js";
import { ref } from "vue";

const props = defineProps<{
  label: string;
  /** Which password this is: the one already set, or a new one (browsers offer to fill or to generate). */
  purpose: "current" | "new";
  errorMessages?: string;
  disabled?: boolean;
}>();

const model = defineModel<string>({ required: true });
const visible = ref(false);
</script>

<template>
  <v-text-field
    v-model="model"
    :label="label"
    :type="visible ? 'text' : 'password'"
    :autocomplete="props.purpose === 'new' ? 'new-password' : 'current-password'"
    :error-messages="errorMessages ?? null"
    :disabled="disabled"
    required
  >
    <template #append-inner>
      <v-btn
        :icon="visible ? mdiEyeOff : mdiEye"
        :aria-label="visible ? 'Hide the password' : 'Show the password'"
        :aria-pressed="visible"
        variant="text"
        size="small"
        density="comfortable"
        @click="visible = !visible"
      />
    </template>
  </v-text-field>
</template>

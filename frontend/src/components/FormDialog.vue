<script setup lang="ts">
// A small dialog around a form: a title, the fields as the default slot, an error line, and a
// submit button that shows it is working. The fields belong to whoever opens it.
defineProps<{
  title: string;
  submitLabel: string;
  busy?: boolean;
  error?: string;
  danger?: boolean;
  /** Keeps the submit button off until something is ticked, say. */
  submitDisabled?: boolean;
  width?: number;
}>();

const open = defineModel<boolean>({ required: true });
defineEmits<{ submit: [] }>();
</script>

<template>
  <v-dialog v-model="open" :max-width="width ?? 460" :persistent="busy" :aria-label="title">
    <v-card :title="title">
      <v-form @submit.prevent="$emit('submit')">
        <v-card-text>
          <v-alert v-if="error" type="error" variant="tonal" class="mb-4" role="alert">
            {{ error }}
          </v-alert>
          <slot />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn :disabled="busy" @click="open = false">Cancel</v-btn>
          <v-btn
            type="submit"
            :color="danger ? 'error' : 'primary'"
            variant="flat"
            :loading="busy"
            :disabled="submitDisabled"
          >
            {{ submitLabel }}
          </v-btn>
        </v-card-actions>
      </v-form>
    </v-card>
  </v-dialog>
</template>

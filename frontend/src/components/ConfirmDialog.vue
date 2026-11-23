<script setup lang="ts">
import { ref, watch } from "vue";
import { describe } from "../api/client";
import FormDialog from "./FormDialog.vue";

// Asks before something that cannot be taken back easily, then runs `action`. A failure stays in
// the dialog, in words, and the dialog stays open so the person can try again or cancel.
const props = defineProps<{
  title: string;
  message: string;
  confirmLabel: string;
  action: () => Promise<void>;
  danger?: boolean;
}>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ done: [] }>();

const busy = ref(false);
const failure = ref("");

watch(
  open,
  (isOpen) => {
    if (isOpen) failure.value = "";
  },
  { immediate: true },
);

async function confirm() {
  busy.value = true;
  failure.value = "";
  try {
    await props.action();
    open.value = false;
    emit("done");
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
    :submit-label="confirmLabel"
    :busy="busy"
    :error="failure"
    :danger="danger"
    @submit="confirm"
  >
    <p class="text-body-2">{{ message }}</p>
  </FormDialog>
</template>

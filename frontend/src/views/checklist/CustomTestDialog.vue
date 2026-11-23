<script setup lang="ts">
import { ref, watch } from "vue";
import { api, describe } from "../../api/client";
import FormDialog from "../../components/FormDialog.vue";

// A test of your own, for something the methodology does not cover.
const props = defineProps<{ pentestId: string; categories: string[] }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ added: [] }>();

const name = ref("");
const category = ref<string | null>("Custom");
const notes = ref("");
const busy = ref(false);
const failure = ref("");

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    name.value = "";
    category.value = "Custom";
    notes.value = "";
    failure.value = "";
  },
  { immediate: true },
);

async function submit() {
  busy.value = true;
  failure.value = "";
  try {
    await api("POST", `/api/pentests/${props.pentestId}/checklist/custom`, {
      name: name.value,
      category: category.value ?? "Custom",
      notes: notes.value,
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
    title="Add a test of your own"
    submit-label="Add test"
    :busy="busy"
    :error="failure"
    @submit="submit"
  >
    <v-text-field v-model="name" label="Name" counter="200" autocomplete="off" />
    <v-combobox
      v-model="category"
      :items="categories"
      label="Category"
      hint="Pick one that is there, or type a new one"
      persistent-hint
      class="mt-4"
    />
    <v-textarea v-model="notes" label="Notes (optional)" auto-grow rows="2" class="mt-4" />
  </FormDialog>
</template>

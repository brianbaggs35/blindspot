<script setup lang="ts">
import { ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { Pentest } from "../../api/types";

// What the target shows. A test that needs a feature the target lacks starts as not applicable,
// so naming the features is how the checklist is cut down to what matters.
const props = defineProps<{
  pentestId: string;
  features: string[];
  suggestions: string[];
  editable: boolean;
}>();
const emit = defineEmits<{ saved: [] }>();

const chosen = ref<string[]>([]);
const busy = ref(false);
const failure = ref("");

watch(
  () => props.features,
  (now) => {
    chosen.value = [...now];
  },
  { immediate: true },
);

async function save() {
  busy.value = true;
  failure.value = "";
  const features = chosen.value.map((one) => one.trim().toLowerCase().replace(/\s+/g, "-"));
  try {
    await api<Pentest>("PATCH", `/api/pentests/${props.pentestId}`, { features });
    emit("saved");
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <v-card border class="mb-4">
    <v-card-item
      title="What the target shows"
      subtitle="Tests that need a feature it lacks start as not applicable"
    />
    <v-card-text>
      <v-alert v-if="failure" type="error" variant="tonal" class="mb-4" role="alert">
        {{ failure }}
      </v-alert>
      <v-form v-if="editable" @submit.prevent="save">
        <v-combobox
          v-model="chosen"
          :items="suggestions"
          label="Features"
          multiple
          chips
          closable-chips
          hint="Such as saml, oauth, jwt, upload or websocket"
          persistent-hint
        />
        <v-btn type="submit" class="mt-4" variant="tonal" :loading="busy">Save features</v-btn>
      </v-form>
      <div v-else-if="features.length > 0" class="d-flex flex-wrap ga-2">
        <v-chip v-for="one in features" :key="one" size="small" label>{{ one }}</v-chip>
      </div>
      <p v-else class="text-body-2 text-medium-emphasis">None named.</p>
    </v-card-text>
  </v-card>
</template>

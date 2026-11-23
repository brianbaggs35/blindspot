<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { Methodology, UpdateCheck } from "../../api/types";
import { isEmptyDiff } from "../../methodologies";

// Looking for an update changes nothing: it shows what would change. Applying names the exact
// update that was shown, so something different is never applied.
const props = defineProps<{ methodology: Methodology }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ applied: [Methodology] }>();

const source = ref<"origin" | "upstream">("origin");
const checked = ref<UpdateCheck | null>(null);
const busy = ref(false);
const failure = ref("");

watch(open, (isOpen) => {
  if (!isOpen) return;
  source.value = "origin";
  checked.value = null;
  failure.value = "";
});

// What an update adds, removes or changes, as lists of names.
const parts = computed(() => {
  const diff = checked.value?.diff;
  if (!diff) return [];
  return [
    { title: "Tests added", items: diff.added },
    { title: "Tests removed", items: diff.removed },
    { title: "Categories added", items: diff.categories_added },
    { title: "Categories removed", items: diff.categories_removed },
    { title: "Details changed", items: diff.details_changed },
  ];
});

async function check() {
  busy.value = true;
  failure.value = "";
  checked.value = null;
  try {
    checked.value = await api<UpdateCheck>(
      "GET",
      `/api/methodologies/${props.methodology.id}/updates?source=${source.value}`,
    );
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}

async function apply() {
  if (checked.value === null) return;
  busy.value = true;
  failure.value = "";
  try {
    const next = await api<Methodology>(
      "POST",
      `/api/methodologies/${props.methodology.id}/updates`,
      {
        source: source.value,
        candidate_hash: checked.value.candidate_hash,
      },
    );
    open.value = false;
    emit("applied", next);
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <v-dialog
    v-model="open"
    max-width="640"
    scrollable
    :persistent="busy"
    :aria-label="`Update ${methodology.name}`"
  >
    <v-card :title="`Update ${methodology.name}`">
      <v-card-text>
        <v-alert v-if="failure" type="error" variant="tonal" class="mb-4" role="alert">
          {{ failure }}
        </v-alert>
        <p class="text-body-2 mb-4">
          Now in use: {{ methodology.version_label }} (version {{ methodology.version_number }}).
          Checking changes nothing; you see what an update would change first.
        </p>
        <v-radio-group
          v-if="methodology.can_update_from_upstream"
          v-model="source"
          label="Where to look"
          :disabled="busy"
          @update:model-value="checked = null"
        >
          <v-radio label="The copy that ships with this release" value="origin" />
          <v-radio label="The latest checklist published by OWASP" value="upstream" />
        </v-radio-group>
        <v-btn :loading="busy" variant="tonal" @click="check">Check for an update</v-btn>

        <div v-if="checked" class="mt-4">
          <p v-if="!checked.changed" class="text-body-1">
            Nothing to update: this is already the latest.
          </p>
          <template v-else>
            <p class="text-body-1 mb-2">
              {{ checked.candidate_label }} would change the following.
            </p>
            <p v-if="isEmptyDiff(checked.diff)" class="text-body-2">
              Only the order or wording inside the methodology differs.
            </p>
            <template v-for="part in parts" :key="part.title">
              <section v-if="part.items.length > 0" class="mb-2">
                <h2 class="text-subtitle-2">{{ part.title }} ({{ part.items.length }})</h2>
                <p class="text-body-2">{{ part.items.join(", ") }}</p>
              </section>
            </template>
            <section v-if="checked.diff.changed.length > 0" class="mb-2">
              <h2 class="text-subtitle-2">Tests changed ({{ checked.diff.changed.length }})</h2>
              <ul class="ps-6 text-body-2">
                <li v-for="one in checked.diff.changed" :key="one.id">
                  {{ one.id }}: {{ one.fields.join(", ") }}
                </li>
              </ul>
            </section>
            <p class="text-body-2 mt-3">
              Playbooks you changed stay as you wrote them. Applying adds a new version; the old one
              is kept.
            </p>
          </template>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn :disabled="busy" @click="open = false">Close</v-btn>
        <v-btn
          v-if="checked?.changed"
          color="primary"
          variant="flat"
          :loading="busy"
          @click="apply"
        >
          Apply this update
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

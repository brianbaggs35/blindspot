<script setup lang="ts">
import { mdiDeleteOutline, mdiPlus } from "@mdi/js";
import { computed, ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { CheckItem, CheckStatus, Evidence } from "../../api/types";
import ConfirmDialog from "../../components/ConfirmDialog.vue";
import { CHECK_CHOICES, CHECK_LABELS } from "../../checklist";

// One test of the checklist: where it stands, what was noticed and what backs it up. A viewer sees
// the same things as plain text. A custom test also has its own name and category.
const props = defineProps<{ pentestId: string; item: CheckItem; editable: boolean }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ saved: [message: string] }>();

const status = ref<CheckStatus>("todo");
const notes = ref("");
const evidence = ref<Evidence[]>([]);
const name = ref("");
const category = ref("");
const busy = ref(false);
const failure = ref("");
const resetOpen = ref(false);

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    failure.value = "";
    status.value = props.item.status;
    notes.value = props.item.notes;
    evidence.value = props.item.evidence.map((one) => ({ ...one }));
    name.value = props.item.name;
    category.value = "";
  },
  { immediate: true },
);

const path = computed(() => `/api/pentests/${props.pentestId}/checklist/${props.item.test_id}`);

function addLink() {
  evidence.value.push({ label: "", url: "" });
}
function linkWords(index: number, part: "label" | "address" | "remove"): string {
  const number = String(index + 1);
  return part === "remove" ? `Remove link ${number}` : `Link ${number} ${part}`;
}
function removeLink(index: number) {
  evidence.value.splice(index, 1);
}

async function save() {
  busy.value = true;
  failure.value = "";
  const links = evidence.value
    .filter((one) => one.label.trim() !== "" || one.url.trim() !== "")
    .map((one) => ({ label: one.label.trim(), url: one.url.trim() }));
  const own = props.item.custom
    ? {
        name: name.value.trim(),
        ...(category.value.trim() === "" ? {} : { category: category.value.trim() }),
      }
    : {};
  try {
    await api("PUT", path.value, {
      status: status.value,
      notes: notes.value,
      evidence: links,
      ...own,
    });
    open.value = false;
    emit("saved", "Saved.");
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}

async function reset() {
  await api("DELETE", path.value);
}
function afterReset() {
  open.value = false;
  emit("saved", props.item.custom ? "Test removed." : "Put back as untouched.");
}
</script>

<template>
  <v-dialog v-model="open" max-width="640" scrollable :persistent="busy" :aria-label="item.name">
    <v-card :title="item.name" :subtitle="item.test_id">
      <v-form @submit.prevent="save">
        <v-card-text>
          <v-alert v-if="failure" type="error" variant="tonal" class="mb-4" role="alert">
            {{ failure }}
          </v-alert>
          <p v-if="!item.applies" class="text-body-2 mb-4">
            This test needs a feature the target does not show: {{ item.requires.join(", ") }}.
          </p>
          <a
            v-if="item.reference"
            :href="item.reference"
            target="_blank"
            rel="noopener noreferrer"
            class="d-inline-block mb-4"
          >
            What the guide says about it
          </a>

          <template v-if="editable">
            <v-text-field
              v-if="item.custom"
              v-model="name"
              label="Name"
              counter="200"
              autocomplete="off"
            />
            <v-text-field
              v-if="item.custom"
              v-model="category"
              label="Move to another category"
              hint="Leave blank to keep it where it is"
              persistent-hint
              autocomplete="off"
              class="mb-4"
            />
            <v-select
              v-model="status"
              :items="CHECK_CHOICES"
              label="Where it stands"
              class="mb-2"
            />
            <v-textarea v-model="notes" label="Notes" auto-grow rows="3" counter="4000" />
            <h2 class="text-subtitle-1 font-weight-bold mt-2">Evidence</h2>
            <p v-if="evidence.length === 0" class="text-body-2 text-medium-emphasis mb-2">
              No links yet.
            </p>
            <div v-for="(link, index) in evidence" :key="index" class="bs-link">
              <v-text-field
                v-model="link.label"
                :label="linkWords(index, 'label')"
                density="compact"
              />
              <v-text-field
                v-model="link.url"
                :label="linkWords(index, 'address')"
                density="compact"
                hint="A web address, http or https"
              />
              <v-btn
                :icon="mdiDeleteOutline"
                variant="text"
                :aria-label="linkWords(index, 'remove')"
                @click="removeLink(index)"
              />
            </div>
            <v-btn variant="tonal" :prepend-icon="mdiPlus" @click="addLink">Add a link</v-btn>
          </template>

          <template v-else>
            <p class="text-body-2">
              <v-chip size="small" label>{{ CHECK_LABELS[item.status] }}</v-chip>
            </p>
            <p v-if="item.notes" class="bs-notes text-body-2 mt-4">{{ item.notes }}</p>
            <ul v-if="item.evidence.length > 0" class="mt-4 pl-4">
              <li v-for="link in item.evidence" :key="link.url">
                <a :href="link.url" target="_blank" rel="noopener noreferrer">{{ link.label }}</a>
              </li>
            </ul>
          </template>
        </v-card-text>
        <v-card-actions>
          <v-btn v-if="editable && (item.touched || item.custom)" @click="resetOpen = true">
            {{ item.custom ? "Remove this test" : "Put back as untouched" }}
          </v-btn>
          <v-spacer />
          <v-btn :disabled="busy" @click="open = false">{{ editable ? "Cancel" : "Close" }}</v-btn>
          <v-btn v-if="editable" type="submit" color="primary" variant="flat" :loading="busy">
            Save
          </v-btn>
        </v-card-actions>
      </v-form>
    </v-card>
    <ConfirmDialog
      v-model="resetOpen"
      :title="item.custom ? 'Remove this test?' : 'Put this test back as untouched?'"
      :message="
        item.custom
          ? 'The test, its notes and its evidence links are deleted.'
          : 'Its state, notes and evidence links are cleared.'
      "
      :confirm-label="item.custom ? 'Remove' : 'Put back'"
      danger
      :action="reset"
      @done="afterReset"
    />
  </v-dialog>
</template>

<style scoped>
.bs-link {
  display: grid;
  grid-template-columns: 1fr 1.6fr auto;
  gap: 8px;
  align-items: start;
}
@media (max-width: 600px) {
  .bs-link {
    grid-template-columns: 1fr;
  }
}
.bs-notes {
  white-space: pre-line;
}
</style>

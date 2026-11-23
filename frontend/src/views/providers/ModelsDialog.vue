<script setup lang="ts">
import { mdiCloudDownloadOutline, mdiPencilOutline, mdiPlus, mdiTrashCanOutline } from "@mdi/js";
import { computed, ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { DiscoveredModel, Provider, ProviderModel } from "../../api/types";
import FormDialog from "../../components/FormDialog.vue";
import StateView from "../../components/StateView.vue";
import { PRICE_SOURCES, priceSummary, tokens } from "../../providers";
import ModelFormDialog from "./ModelFormDialog.vue";

// A provider's models: the ones in use, what the provider offers that is not added yet, and (for
// an administrator) the way to add, change and remove them.
const props = defineProps<{ provider: Provider; canEdit: boolean }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ changed: [] }>();

const models = ref<ProviderModel[]>([]);
const state = ref<"loading" | "error" | "ready">("loading");
const failure = ref("");
const notice = ref("");

let latest = 0;
async function load() {
  const mine = ++latest;
  state.value = "loading";
  try {
    const rows = await api<ProviderModel[]>("GET", `/api/providers/${props.provider.id}/models`);
    if (mine !== latest) return;
    models.value = rows;
    state.value = "ready";
  } catch (error) {
    if (mine !== latest) return;
    failure.value = describe(error);
    state.value = "error";
  }
}

const offered = ref<DiscoveredModel[]>([]);
const fetched = ref(false);
const picked = ref<string[]>([]);
const fetching = ref(false);
const fetchFailure = ref("");
const adding = ref(false);

// Opening the dialog starts from a fresh look at the provider. It is created already open the
// first time, hence `immediate`.
watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    offered.value = [];
    fetched.value = false;
    picked.value = [];
    fetchFailure.value = "";
    notice.value = "";
    void load();
  },
  { immediate: true },
);

const fresh = computed(() => offered.value.filter((one) => !one.added));

async function fetchModels() {
  fetching.value = true;
  fetchFailure.value = "";
  try {
    offered.value = await api<DiscoveredModel[]>(
      "POST",
      `/api/providers/${props.provider.id}/models/fetch`,
    );
    fetched.value = true;
    picked.value = [];
  } catch (error) {
    fetchFailure.value = describe(error);
  } finally {
    fetching.value = false;
  }
}

async function addPicked() {
  adding.value = true;
  fetchFailure.value = "";
  try {
    const chosen = fresh.value.filter((found) => picked.value.includes(found.model_id));
    await Promise.all(
      chosen.map((one) =>
        api("POST", `/api/providers/${props.provider.id}/models`, {
          model_id: one.model_id,
          display_name: one.display_name,
          context_tokens: one.context_tokens,
          max_output_tokens: one.max_output_tokens,
          capabilities: one.capabilities,
        }),
      ),
    );
    const count = picked.value.length;
    notice.value = `Added ${String(count)} ${count === 1 ? "model" : "models"}.`;
    fetched.value = false;
    picked.value = [];
    emit("changed");
    await load();
  } catch (error) {
    fetchFailure.value = describe(error);
  } finally {
    adding.value = false;
  }
}

const formOpen = ref(false);
const editing = ref<ProviderModel | null>(null);
function openForm(model: ProviderModel | null) {
  editing.value = model;
  formOpen.value = true;
}
async function saved(model: ProviderModel) {
  notice.value = `Saved ${model.display_name}.`;
  emit("changed");
  await load();
}

async function toggle(model: ProviderModel, enabled: boolean | null) {
  try {
    await api("PATCH", `/api/providers/${model.provider_id}/models/${model.id}`, {
      enabled: enabled === true,
    });
    emit("changed");
    await load();
  } catch (error) {
    notice.value = describe(error);
  }
}

const removing = ref<ProviderModel | null>(null);
const removeOpen = ref(false);
const removeBusy = ref(false);
const removeError = ref("");
function askRemove(model: ProviderModel) {
  removing.value = model;
  removeError.value = "";
  removeOpen.value = true;
}
async function remove() {
  const model = removing.value;
  if (model === null) return;
  removeBusy.value = true;
  try {
    await api("DELETE", `/api/providers/${model.provider_id}/models/${model.id}`);
    removeOpen.value = false;
    notice.value = `Removed ${model.display_name}.`;
    emit("changed");
    await load();
  } catch (error) {
    removeError.value = describe(error);
  } finally {
    removeBusy.value = false;
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="760" scrollable>
    <v-card :title="`Models of ${provider.name}`">
      <v-card-text>
        <v-alert v-if="notice" type="info" variant="tonal" class="mb-4" density="compact">
          {{ notice }}
        </v-alert>
        <div v-if="canEdit" class="d-flex flex-wrap ga-2 mb-4">
          <v-btn
            variant="tonal"
            :prepend-icon="mdiCloudDownloadOutline"
            :loading="fetching"
            @click="fetchModels"
          >
            Fetch models
          </v-btn>
          <v-btn variant="tonal" :prepend-icon="mdiPlus" @click="openForm(null)">
            Add by hand
          </v-btn>
        </div>

        <section v-if="fetched" class="mb-4" aria-label="Models the provider offers">
          <h2 class="text-subtitle-1 mb-2">The provider offers {{ offered.length }} models</h2>
          <p v-if="fresh.length === 0" class="text-body-2 text-medium-emphasis">
            Every one of them is added already.
          </p>
          <template v-else>
            <v-checkbox
              v-for="one in fresh"
              :key="one.model_id"
              v-model="picked"
              :value="one.model_id"
              density="compact"
              hide-details
            >
              <template #label>
                <span>
                  {{ one.display_name }}
                  <span class="text-medium-emphasis">
                    · {{ one.model_id }} · {{ PRICE_SOURCES[one.price_source].label }}
                  </span>
                </span>
              </template>
            </v-checkbox>
            <v-btn
              class="mt-3"
              color="primary"
              :disabled="picked.length === 0"
              :loading="adding"
              @click="addPicked"
            >
              Add {{ picked.length }} selected
            </v-btn>
          </template>
        </section>
        <v-alert v-if="fetchFailure" type="error" variant="tonal" class="mb-4">
          {{ fetchFailure }}
        </v-alert>

        <StateView
          :state="state === 'ready' && models.length === 0 ? 'empty' : state"
          :title="state === 'error' ? 'Could not load the models' : 'No models yet'"
          :message="
            state === 'error'
              ? failure
              : canEdit
                ? 'Fetch the models this provider offers, or add one by hand.'
                : 'An administrator has not added any.'
          "
          :action-label="state === 'error' ? 'Try again' : undefined"
          @action="load"
        >
          <v-list lines="two" class="pa-0" aria-label="Models">
            <v-list-item
              v-for="model in models"
              :key="model.id"
              :title="model.display_name"
              :subtitle="`${model.model_id} · ${tokens(model.context_tokens)} · ${priceSummary(model.price)}`"
            >
              <template #append>
                <v-chip
                  size="small"
                  label
                  class="mr-2"
                  :title="PRICE_SOURCES[model.price_source].hint"
                >
                  {{ PRICE_SOURCES[model.price_source].label }}
                </v-chip>
                <v-chip
                  v-if="!model.supports_tools"
                  size="small"
                  label
                  color="warning"
                  class="mr-2"
                >
                  no tools
                </v-chip>
                <v-switch
                  :model-value="model.enabled"
                  :disabled="!canEdit"
                  :aria-label="`Use ${model.display_name}`"
                  color="primary"
                  density="compact"
                  hide-details
                  inset
                  @update:model-value="(value) => toggle(model, value)"
                />
                <template v-if="canEdit">
                  <v-btn
                    :icon="mdiPencilOutline"
                    variant="text"
                    size="small"
                    :aria-label="`Edit ${model.display_name}`"
                    @click="openForm(model)"
                  />
                  <v-btn
                    :icon="mdiTrashCanOutline"
                    variant="text"
                    size="small"
                    :aria-label="`Remove ${model.display_name}`"
                    @click="askRemove(model)"
                  />
                </template>
              </template>
            </v-list-item>
          </v-list>
        </StateView>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="open = false">Close</v-btn>
      </v-card-actions>
    </v-card>

    <ModelFormDialog
      v-model="formOpen"
      :provider-id="provider.id"
      :model="editing"
      @saved="saved"
    />
    <FormDialog
      v-model="removeOpen"
      :title="`Remove ${removing?.display_name ?? ''}?`"
      submit-label="Remove"
      :busy="removeBusy"
      :error="removeError"
      danger
      @submit="remove"
    >
      <p class="text-body-2">
        The model is taken off this list. Anything that used it as a default is cleared. Calls
        already made stay in the usage history.
      </p>
    </FormDialog>
  </v-dialog>
</template>

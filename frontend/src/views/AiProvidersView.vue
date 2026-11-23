<script setup lang="ts">
import { mdiPlus } from "@mdi/js";
import { computed, onMounted, ref } from "vue";
import { api, describe } from "../api/client";
import type { KindInfo, Provider, ProviderModel, RoleDefault } from "../api/types";
import FormDialog from "../components/FormDialog.vue";
import PageHeader from "../components/PageHeader.vue";
import StateView from "../components/StateView.vue";
import { useAuthStore } from "../stores/auth";
import ModelsDialog from "./providers/ModelsDialog.vue";
import ProviderCard from "./providers/ProviderCard.vue";
import ProviderFormDialog from "./providers/ProviderFormDialog.vue";
import RoleDefaults from "./providers/RoleDefaults.vue";

const auth = useAuthStore();
const canEdit = computed(() => auth.isAdmin);

const kinds = ref<KindInfo[]>([]);
const providers = ref<Provider[]>([]);
const models = ref<ProviderModel[]>([]);
const roles = ref<RoleDefault[]>([]);
const state = ref<"loading" | "error" | "ready">("loading");
const failure = ref("");
const notice = ref("");
const noticeOpen = ref(false);

function tell(message: string) {
  notice.value = message;
  noticeOpen.value = true;
}

// The first load shows the page's skeleton; later ones refresh in place.
let latest = 0;
async function load(quiet = false) {
  const mine = ++latest;
  if (!quiet) state.value = "loading";
  try {
    const [nextKinds, nextProviders, nextRoles] = await Promise.all([
      api<KindInfo[]>("GET", "/api/ai/kinds"),
      api<Provider[]>("GET", "/api/providers"),
      api<RoleDefault[]>("GET", "/api/ai/role-defaults"),
    ]);
    const lists = await Promise.all(
      nextProviders.map((one) => api<ProviderModel[]>("GET", `/api/providers/${one.id}/models`)),
    );
    if (mine !== latest) return;
    kinds.value = nextKinds;
    providers.value = nextProviders;
    roles.value = nextRoles;
    models.value = lists.flat();
    state.value = "ready";
  } catch (error) {
    if (mine !== latest) return;
    failure.value = describe(error);
    state.value = "error";
  }
}

const formOpen = ref(false);
const editing = ref<Provider | null>(null);
function openForm(provider: Provider | null) {
  editing.value = provider;
  formOpen.value = true;
}
async function saved(provider: Provider) {
  const added = editing.value === null;
  await load(true);
  tell(added ? `Added ${provider.name}. Fetch its models next.` : `Saved ${provider.name}.`);
}

const modelsOpen = ref(false);
const viewing = ref<Provider | null>(null);
function openModels(provider: Provider) {
  viewing.value = provider;
  modelsOpen.value = true;
}

const removeOpen = ref(false);
const removing = ref<Provider | null>(null);
const removeBusy = ref(false);
const removeError = ref("");
function askRemove(provider: Provider) {
  removing.value = provider;
  removeError.value = "";
  removeOpen.value = true;
}
async function remove() {
  const provider = removing.value;
  if (provider === null) return;
  removeBusy.value = true;
  try {
    await api("DELETE", `/api/providers/${provider.id}`);
    removeOpen.value = false;
    await load(true);
    tell(`Deleted ${provider.name}.`);
  } catch (error) {
    removeError.value = describe(error);
  } finally {
    removeBusy.value = false;
  }
}

const kindOf = (provider: Provider) => kinds.value.find((one) => one.kind === provider.kind);

onMounted(() => load());
</script>

<template>
  <v-container>
    <PageHeader
      title="AI providers"
      subtitle="Where Blindspot's agents get their models, and what they may spend."
    >
      <template #actions>
        <v-btn v-if="canEdit" color="primary" :prepend-icon="mdiPlus" @click="openForm(null)">
          Add a provider
        </v-btn>
      </template>
    </PageHeader>

    <StateView
      :state="state === 'ready' && providers.length === 0 ? 'empty' : state"
      :title="state === 'error' ? 'Could not load the providers' : 'No AI providers yet'"
      :message="
        state === 'error'
          ? failure
          : canEdit
            ? 'Add Anthropic, OpenAI or Ollama to give the agents a model.'
            : 'An administrator has not added one yet.'
      "
      :action-label="state === 'error' ? 'Try again' : undefined"
      @action="load()"
    >
      <v-row class="mb-6">
        <v-col v-for="provider in providers" :key="provider.id" cols="12" md="6" xl="4">
          <ProviderCard
            :provider="provider"
            :kind="kindOf(provider)"
            :can-edit="canEdit"
            @models="openModels(provider)"
            @edit="openForm(provider)"
            @remove="askRemove(provider)"
          />
        </v-col>
      </v-row>
      <RoleDefaults
        :roles="roles"
        :providers="providers"
        :models="models"
        :can-edit="canEdit"
        @changed="(job) => tell(`Saved the default for ${job.toLowerCase()}.`)"
      />
    </StateView>

    <ProviderFormDialog v-model="formOpen" :provider="editing" :kinds="kinds" @saved="saved" />
    <ModelsDialog
      v-if="viewing"
      v-model="modelsOpen"
      :provider="viewing"
      :can-edit="canEdit"
      @changed="load(true)"
    />
    <FormDialog
      v-model="removeOpen"
      :title="`Delete ${removing?.name ?? ''}?`"
      submit-label="Delete"
      :busy="removeBusy"
      :error="removeError"
      danger
      @submit="remove"
    >
      <p class="text-body-2">
        The provider, its saved key and its models are removed, and any default that used one of its
        models is cleared. What it cost stays in the usage history.
      </p>
    </FormDialog>
    <v-snackbar v-model="noticeOpen" :timeout="5000">{{ notice }}</v-snackbar>
  </v-container>
</template>

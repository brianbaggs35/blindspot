<script setup lang="ts">
import { mdiKeyOutline } from "@mdi/js";
import { onMounted, ref } from "vue";
import { api, describe } from "../../api/client";
import type { PasskeyInfo } from "../../api/types";
import FormDialog from "../../components/FormDialog.vue";
import PasswordField from "../../components/PasswordField.vue";
import StateView from "../../components/StateView.vue";
import { formatWhen } from "../../format";
import { addPasskey, PasskeyCancelled, passkeysSupported } from "../../passkeys";

type Dialog = "add" | "rename" | "remove";

const passkeys = ref<PasskeyInfo[]>([]);
const state = ref<"loading" | "error" | "ready">("loading");
const failure = ref("");
const supported = passkeysSupported();

const dialog = ref<Dialog>("add");
const open = ref(false);
const targetId = ref("");
const targetName = ref("");
const name = ref("");
const password = ref("");
const busy = ref(false);
const dialogError = ref("");

async function load() {
  state.value = "loading";
  try {
    passkeys.value = await api<PasskeyInfo[]>("GET", "/api/auth/passkeys");
    state.value = "ready";
  } catch (error) {
    failure.value = describe(error);
    state.value = "error";
  }
}

function show(kind: Dialog, passkey?: PasskeyInfo) {
  dialog.value = kind;
  targetId.value = passkey?.id ?? "";
  targetName.value = passkey?.name ?? "";
  name.value = passkey?.name ?? "My passkey";
  password.value = "";
  dialogError.value = "";
  open.value = true;
}

async function submit() {
  busy.value = true;
  dialogError.value = "";
  try {
    if (dialog.value === "add") await addPasskey(name.value, password.value);
    else if (dialog.value === "rename") {
      await api("PATCH", `/api/auth/passkeys/${targetId.value}`, { name: name.value });
    } else {
      await api("DELETE", `/api/auth/passkeys/${targetId.value}`, {
        password: password.value,
      });
    }
    open.value = false;
    await load();
  } catch (error) {
    dialogError.value = error instanceof PasskeyCancelled ? error.message : describe(error);
  } finally {
    busy.value = false;
  }
}

const titles = { add: "Add a passkey", rename: "Rename the passkey", remove: "Remove the passkey" };
const labels = { add: "Add passkey", rename: "Rename", remove: "Remove" };

onMounted(load);
</script>

<template>
  <v-card border>
    <v-card-title tag="h2" class="text-h6 d-flex align-center">
      Passkeys
      <v-spacer />
      <v-btn v-if="supported" size="small" color="primary" variant="tonal" @click="show('add')">
        Add a passkey
      </v-btn>
    </v-card-title>
    <v-card-text>
      <p v-if="!supported" class="text-body-2 text-medium-emphasis mb-3">
        This browser cannot make passkeys. You can still manage the ones you have.
      </p>
      <StateView
        :state="state === 'ready' && passkeys.length === 0 ? 'empty' : state"
        :title="state === 'error' ? 'Could not load your passkeys' : 'No passkeys yet'"
        :message="
          state === 'error'
            ? failure
            : 'A passkey lets you sign in with your device instead of a password.'
        "
        :action-label="state === 'error' ? 'Try again' : undefined"
        @action="load"
      >
        <v-list lines="two" class="pa-0">
          <v-list-item
            v-for="passkey in passkeys"
            :key="passkey.id"
            :prepend-icon="mdiKeyOutline"
            :title="passkey.name"
            :subtitle="`Added ${formatWhen(passkey.created_at)} · last used ${formatWhen(passkey.last_used_at)}`"
          >
            <template #append>
              <v-btn
                size="small"
                variant="text"
                :aria-label="`Rename ${passkey.name}`"
                @click="show('rename', passkey)"
              >
                Rename
              </v-btn>
              <v-btn
                size="small"
                variant="text"
                color="error"
                :aria-label="`Remove ${passkey.name}`"
                @click="show('remove', passkey)"
              >
                Remove
              </v-btn>
            </template>
          </v-list-item>
        </v-list>
      </StateView>
    </v-card-text>

    <FormDialog
      v-model="open"
      :title="titles[dialog]"
      :submit-label="labels[dialog]"
      :busy="busy"
      :error="dialogError"
      :danger="dialog === 'remove'"
      @submit="submit"
    >
      <p v-if="dialog === 'remove'" class="mb-4">
        Remove “{{ targetName }}”? You will not be able to sign in with it any more.
      </p>
      <v-text-field
        v-if="dialog !== 'remove'"
        v-model="name"
        label="Name"
        maxlength="64"
        required
      />
      <PasswordField
        v-if="dialog !== 'rename'"
        v-model="password"
        label="Your password"
        autocomplete="current-password"
      />
    </FormDialog>
  </v-card>
</template>

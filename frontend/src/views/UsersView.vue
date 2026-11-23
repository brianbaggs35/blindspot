<script setup lang="ts">
import {
  mdiAccountPlusOutline,
  mdiAccountRemoveOutline,
  mdiDotsVertical,
  mdiLockReset,
  mdiLogoutVariant,
  mdiPencilOutline,
} from "@mdi/js";
import { onMounted, ref } from "vue";
import { api, describe } from "../api/client";
import type { User } from "../api/types";
import FormDialog from "../components/FormDialog.vue";
import PageHeader from "../components/PageHeader.vue";
import StateView from "../components/StateView.vue";
import { formatWhen } from "../format";
import { useAuthStore } from "../stores/auth";
import ResetPasswordDialog from "./users/ResetPasswordDialog.vue";
import UserFormDialog from "./users/UserFormDialog.vue";

const auth = useAuthStore();
const users = ref<User[]>([]);
const state = ref<"loading" | "error" | "ready">("loading");
const failure = ref("");
const notice = ref("");
const noticeOpen = ref(false);

let latest = 0;
async function load() {
  const mine = ++latest;
  state.value = "loading";
  try {
    const rows = await api<User[]>("GET", "/api/users");
    if (mine !== latest) return;
    users.value = rows;
    state.value = "ready";
  } catch (error) {
    if (mine !== latest) return;
    failure.value = describe(error);
    state.value = "error";
  }
}

function tell(message: string) {
  notice.value = message;
  noticeOpen.value = true;
}

// The form dialog adds when `editing` is null and changes that account otherwise.
const formOpen = ref(false);
const editing = ref<User | null>(null);
function openForm(user: User | null) {
  editing.value = user;
  formOpen.value = true;
}
async function saved(user: User) {
  await load();
  tell(editing.value === null ? `Added ${user.username}.` : `Saved ${user.username}.`);
}

const resetOpen = ref(false);
const resetting = ref<User | null>(null);
function openReset(user: User) {
  resetting.value = user;
  resetOpen.value = true;
}

// Sign out and delete ask first, in the same dialog.
interface Confirmation {
  user: User;
  kind: "sign-out" | "delete";
}
const confirmOpen = ref(false);
const confirming = ref<Confirmation | null>(null);
const confirmBusy = ref(false);
const confirmError = ref("");
function ask(user: User, kind: Confirmation["kind"]) {
  confirming.value = { user, kind };
  confirmError.value = "";
  confirmOpen.value = true;
}
async function confirm() {
  const pending = confirming.value;
  if (pending === null) return;
  confirmBusy.value = true;
  confirmError.value = "";
  try {
    if (pending.kind === "delete") {
      await api("DELETE", `/api/users/${pending.user.id}`);
    } else {
      await api("POST", `/api/users/${pending.user.id}/sign-out`);
    }
    confirmOpen.value = false;
    if (pending.kind === "delete") await load();
    tell(
      pending.kind === "delete"
        ? `Deleted ${pending.user.username}.`
        : `${pending.user.username} was signed out everywhere.`,
    );
  } catch (error) {
    confirmError.value = describe(error);
  } finally {
    confirmBusy.value = false;
  }
}

const isSelf = (user: User) => user.id === auth.user?.id;

onMounted(load);
</script>

<template>
  <v-container>
    <PageHeader title="Users" subtitle="Who can sign in to Blindspot, and what they may do.">
      <template #actions>
        <v-btn color="primary" :prepend-icon="mdiAccountPlusOutline" @click="openForm(null)">
          Add a user
        </v-btn>
      </template>
    </PageHeader>

    <StateView
      :state="state === 'ready' && users.length === 0 ? 'empty' : state"
      :title="state === 'error' ? 'Could not load the users' : 'No users'"
      :message="state === 'error' ? failure : 'Add the first user.'"
      :action-label="state === 'error' ? 'Try again' : undefined"
      @action="load"
    >
      <v-card border>
        <v-list lines="two" class="pa-0" aria-label="Users">
          <v-list-item
            v-for="user in users"
            :key="user.id"
            :title="user.display_name || user.username"
            :subtitle="`${user.username} · last signed in ${formatWhen(user.last_sign_in_at)}`"
          >
            <template #append>
              <v-chip size="small" label class="mr-2">{{ user.role }}</v-chip>
              <v-chip v-if="!user.is_active" size="small" label color="warning" class="mr-2">
                disabled
              </v-chip>
              <v-chip v-if="isSelf(user)" size="small" label color="primary" class="mr-2">
                you
              </v-chip>
              <v-menu>
                <template #activator="{ props: activator }">
                  <v-btn
                    v-bind="activator"
                    :icon="mdiDotsVertical"
                    variant="text"
                    size="small"
                    :aria-label="`Actions for ${user.username}`"
                  />
                </template>
                <v-list>
                  <v-list-item :prepend-icon="mdiPencilOutline" @click="openForm(user)">
                    Edit
                  </v-list-item>
                  <v-list-item :prepend-icon="mdiLockReset" @click="openReset(user)">
                    Reset password
                  </v-list-item>
                  <v-list-item :prepend-icon="mdiLogoutVariant" @click="ask(user, 'sign-out')">
                    Sign out everywhere
                  </v-list-item>
                  <v-list-item
                    :prepend-icon="mdiAccountRemoveOutline"
                    :disabled="isSelf(user)"
                    base-color="error"
                    @click="ask(user, 'delete')"
                  >
                    Delete
                  </v-list-item>
                </v-list>
              </v-menu>
            </template>
          </v-list-item>
        </v-list>
      </v-card>
    </StateView>

    <UserFormDialog
      v-model="formOpen"
      :user="editing"
      :is-self="editing !== null && isSelf(editing)"
      @saved="saved"
    />
    <ResetPasswordDialog
      v-model="resetOpen"
      :user="resetting"
      @done="(user) => tell(`${user.username} was signed out everywhere and has the new password.`)"
    />
    <FormDialog
      v-model="confirmOpen"
      :title="
        confirming?.kind === 'delete'
          ? `Delete ${confirming.user.username}?`
          : `Sign ${confirming?.user.username ?? ''} out everywhere?`
      "
      :submit-label="confirming?.kind === 'delete' ? 'Delete' : 'Sign out everywhere'"
      :busy="confirmBusy"
      :error="confirmError"
      danger
      @submit="confirm"
    >
      <p class="text-body-2">
        {{
          confirming?.kind === "delete"
            ? "The account is removed for good. What it did stays in the audit log."
            : "Every browser this person is signed in on is signed out. They can sign in again."
        }}
      </p>
    </FormDialog>
    <v-snackbar v-model="noticeOpen" :timeout="5000">{{ notice }}</v-snackbar>
  </v-container>
</template>

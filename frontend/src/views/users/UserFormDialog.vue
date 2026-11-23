<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { Role, User } from "../../api/types";
import FormDialog from "../../components/FormDialog.vue";
import PasswordField from "../../components/PasswordField.vue";
import PasswordRules from "../../components/PasswordRules.vue";
import { allMet, passwordRules } from "../../passwords";

// Adds an account, or changes one. Changing your own role or status is refused by the API, so the
// fields are off for your own account and say why.
const props = defineProps<{ user: User | null; isSelf: boolean }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ saved: [User] }>();

const roles: { title: string; value: Role }[] = [
  { title: "Viewer: can look, not change", value: "viewer" },
  { title: "Administrator: can change everything", value: "admin" },
];

const username = ref("");
const displayName = ref("");
const role = ref<Role>("viewer");
const active = ref(true);
const password = ref("");
const busy = ref(false);
const failure = ref("");

const editing = computed(() => props.user !== null);
const title = computed(() => (props.user === null ? "Add a user" : `Edit ${props.user.username}`));

// Each time the dialog opens it starts from the account (or from nothing).
watch(open, (isOpen) => {
  if (!isOpen) return;
  failure.value = "";
  password.value = "";
  username.value = props.user?.username ?? "";
  displayName.value = props.user?.display_name ?? "";
  role.value = props.user?.role ?? "viewer";
  active.value = props.user?.is_active ?? true;
});

async function submit() {
  failure.value = "";
  if (props.user === null && !allMet(passwordRules(password.value, username.value))) {
    failure.value = "Check the password rules.";
    return;
  }
  busy.value = true;
  try {
    const saved =
      props.user === null
        ? await api<User>("POST", "/api/users", {
            username: username.value,
            display_name: displayName.value,
            role: role.value,
            password: password.value,
          })
        : await api<User>("PATCH", `/api/users/${props.user.id}`, {
            display_name: displayName.value,
            ...(props.isSelf ? {} : { role: role.value, is_active: active.value }),
          });
    open.value = false;
    emit("saved", saved);
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
    :submit-label="editing ? 'Save' : 'Add user'"
    :busy="busy"
    :error="failure"
    @submit="submit"
  >
    <v-text-field
      v-if="!editing"
      v-model="username"
      label="Username"
      autocomplete="off"
      hint="3 to 64 letters, digits, dots, dashes or underscores"
      persistent-hint
      required
      class="mb-2"
    />
    <v-text-field
      v-model="displayName"
      label="Name"
      autocomplete="off"
      hint="Shown instead of the username. Optional."
      persistent-hint
      class="mb-2"
    />
    <v-select
      v-model="role"
      :items="roles"
      label="Role"
      :disabled="isSelf"
      :hint="isSelf ? 'You cannot change your own role.' : ''"
      :persistent-hint="isSelf"
      class="mb-2"
    />
    <v-switch
      v-if="editing"
      v-model="active"
      label="Can sign in"
      color="primary"
      :disabled="isSelf"
      :hint="isSelf ? 'You cannot disable your own account.' : ''"
      :persistent-hint="isSelf"
      inset
    />
    <template v-if="!editing">
      <PasswordField v-model="password" label="Password" purpose="new" />
      <PasswordRules :password="password" :username="username" />
    </template>
  </FormDialog>
</template>

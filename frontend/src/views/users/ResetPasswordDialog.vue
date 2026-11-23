<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { api, describe } from "../../api/client";
import type { User } from "../../api/types";
import FormDialog from "../../components/FormDialog.vue";
import PasswordField from "../../components/PasswordField.vue";
import PasswordRules from "../../components/PasswordRules.vue";
import { allMet, passwordRules } from "../../passwords";

// An administrator sets a new password for someone; every browser that person is signed in on is
// signed out.
const props = defineProps<{ user: User | null }>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ done: [User] }>();

const password = ref("");
const username = computed(() => props.user?.username ?? "");
const busy = ref(false);
const failure = ref("");

watch(open, (isOpen) => {
  if (!isOpen) return;
  password.value = "";
  failure.value = "";
});

async function submit() {
  if (props.user === null) return;
  failure.value = "";
  if (!allMet(passwordRules(password.value, username.value))) {
    failure.value = "Check the password rules.";
    return;
  }
  busy.value = true;
  try {
    await api("POST", `/api/users/${props.user.id}/password`, { password: password.value });
    open.value = false;
    emit("done", props.user);
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
    :title="`Reset the password for ${username}`"
    submit-label="Reset password"
    :busy="busy"
    :error="failure"
    @submit="submit"
  >
    <p class="text-body-2 mb-3">They will be signed out everywhere and need the new password.</p>
    <PasswordField v-model="password" label="New password" autocomplete="new-password" />
    <PasswordRules :password="password" :username="username" />
  </FormDialog>
</template>

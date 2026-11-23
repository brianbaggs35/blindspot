<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { describe } from "../api/client";
import AuthCard from "../components/AuthCard.vue";
import PasswordField from "../components/PasswordField.vue";
import PasswordRules from "../components/PasswordRules.vue";
import { allMet, passwordRules } from "../passwords";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const router = useRouter();

const code = ref("");
const username = ref("");
const displayName = ref("");
const password = ref("");
const confirmation = ref("");
const busy = ref(false);
const failure = ref("");

const mismatch = computed(() =>
  confirmation.value !== "" && confirmation.value !== password.value
    ? "The two passwords are different."
    : "",
);

async function submit() {
  failure.value = "";
  if (
    !allMet(passwordRules(password.value, username.value)) ||
    confirmation.value !== password.value
  ) {
    failure.value = "Check the password rules and type the password twice, the same.";
    return;
  }
  busy.value = true;
  try {
    await auth.setup({
      setup_code: code.value,
      username: username.value,
      display_name: displayName.value,
      password: password.value,
    });
    await router.push("/");
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <AuthCard
    title="Set up Blindspot"
    subtitle="Create the first administrator. There are no default passwords."
  >
    <v-card variant="tonal" color="info" class="pa-3 mb-4 text-body-2">
      The setup code was printed in the container's log when it started. Run
      <code>docker logs blindspot</code> and look for “setup_required”.
    </v-card>
    <v-alert v-if="failure" type="error" variant="tonal" class="mb-4" role="alert">
      {{ failure }}
    </v-alert>
    <v-form @submit.prevent="submit">
      <v-text-field
        v-model="code"
        label="Setup code"
        autocomplete="off"
        autocapitalize="characters"
        spellcheck="false"
        class="mono"
        required
      />
      <v-text-field
        v-model="username"
        label="Username"
        hint="Lowercase letters, numbers, dots, dashes and underscores"
        autocomplete="username"
        autocapitalize="none"
        spellcheck="false"
        required
      />
      <v-text-field v-model="displayName" label="Name (optional)" autocomplete="name" />
      <PasswordField v-model="password" label="Password" purpose="new" />
      <PasswordRules :password="password" :username="username" />
      <PasswordField
        v-model="confirmation"
        label="Type the password again"
        purpose="new"
        :error-messages="mismatch"
        class="mt-4"
      />
      <v-btn type="submit" color="primary" size="large" block :loading="busy" class="mt-2">
        Create the administrator
      </v-btn>
    </v-form>
  </AuthCard>
</template>

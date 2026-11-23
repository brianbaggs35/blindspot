<script setup lang="ts">
import { mdiKeyOutline } from "@mdi/js";
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { describe } from "../api/client";
import AuthCard from "../components/AuthCard.vue";
import PasswordField from "../components/PasswordField.vue";
import { PasskeyCancelled, passkeysSupported } from "../passkeys";
import { safeNext } from "../router/guard";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const username = ref("");
const password = ref("");
const busy = ref(false);
const failure = ref("");
const canUsePasskeys = passkeysSupported();

async function attempt(action: () => Promise<void>) {
  busy.value = true;
  failure.value = "";
  try {
    await action();
    await router.push(safeNext(route.query["next"]));
  } catch (error) {
    failure.value = error instanceof PasskeyCancelled ? error.message : describe(error);
  } finally {
    busy.value = false;
  }
}

const submit = () => attempt(() => auth.signIn(username.value, password.value));
const usePasskey = () => attempt(() => auth.signInWithPasskey());
</script>

<template>
  <AuthCard title="Sign in to Blindspot">
    <v-alert v-if="failure" type="error" variant="tonal" class="mb-4" role="alert">
      {{ failure }}
    </v-alert>
    <v-form @submit.prevent="submit">
      <v-text-field
        v-model="username"
        label="Username"
        autocomplete="username"
        autocapitalize="none"
        spellcheck="false"
        required
      />
      <PasswordField v-model="password" label="Password" purpose="current" />
      <v-btn type="submit" color="primary" size="large" block :loading="busy" class="mt-2">
        Sign in
      </v-btn>
    </v-form>
    <template v-if="canUsePasskeys">
      <v-divider class="my-4" />
      <v-btn
        variant="tonal"
        block
        :prepend-icon="mdiKeyOutline"
        :disabled="busy"
        @click="usePasskey"
      >
        Sign in with a passkey
      </v-btn>
    </template>
  </AuthCard>
</template>

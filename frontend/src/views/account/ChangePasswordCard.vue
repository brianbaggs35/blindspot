<script setup lang="ts">
import { computed, ref } from "vue";
import { api, describe } from "../../api/client";
import PasswordField from "../../components/PasswordField.vue";
import PasswordRules from "../../components/PasswordRules.vue";
import { allMet, passwordRules } from "../../passwords";
import { useAuthStore } from "../../stores/auth";

const auth = useAuthStore();
const current = ref("");
const fresh = ref("");
const again = ref("");
const busy = ref(false);
const failure = ref("");
const done = ref(false);

const username = computed(() => auth.user?.username ?? "");
const mismatch = computed(() =>
  again.value !== "" && again.value !== fresh.value ? "The two passwords are different." : "",
);

async function submit() {
  done.value = false;
  failure.value = "";
  if (!allMet(passwordRules(fresh.value, username.value)) || again.value !== fresh.value) {
    failure.value = "Check the password rules and type the new password twice, the same.";
    return;
  }
  busy.value = true;
  try {
    await api("POST", "/api/auth/password", {
      current_password: current.value,
      new_password: fresh.value,
    });
    current.value = fresh.value = again.value = "";
    done.value = true;
  } catch (error) {
    failure.value = describe(error);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <v-card border>
    <v-card-title tag="h2" class="text-h6">Change your password</v-card-title>
    <v-card-text>
      <v-alert v-if="done" type="success" variant="tonal" class="mb-4" role="status">
        Password changed. Your other browsers were signed out.
      </v-alert>
      <v-alert v-if="failure" type="error" variant="tonal" class="mb-4" role="alert">
        {{ failure }}
      </v-alert>
      <v-form @submit.prevent="submit">
        <PasswordField v-model="current" label="Current password" autocomplete="current-password" />
        <PasswordField v-model="fresh" label="New password" autocomplete="new-password" />
        <PasswordRules :password="fresh" :username="username" />
        <PasswordField
          v-model="again"
          label="Type the new password again"
          autocomplete="new-password"
          :error-messages="mismatch"
          class="mt-4"
        />
        <v-btn type="submit" color="primary" :loading="busy">Change password</v-btn>
      </v-form>
    </v-card-text>
  </v-card>
</template>

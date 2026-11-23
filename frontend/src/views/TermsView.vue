<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, describe } from "../api/client";
import type { Terms } from "../api/types";
import AuthCard from "../components/AuthCard.vue";
import StateView from "../components/StateView.vue";
import { safeNext } from "../router/guard";
import { useAuthStore } from "../stores/auth";

// The terms of use, which everybody accepts before they can use the app, and again whenever the
// words change. The text comes from the API so there is one copy of it.
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const terms = ref<Terms | null>(null);
const state = ref<"loading" | "error" | "ready">("loading");
const failure = ref("");
const agreed = ref(false);
const busy = ref(false);
const problem = ref("");

async function load() {
  state.value = "loading";
  try {
    terms.value = await api<Terms>("GET", "/api/terms");
    state.value = "ready";
  } catch (error) {
    failure.value = describe(error);
    state.value = "error";
  }
}

async function accept(version: string) {
  busy.value = true;
  problem.value = "";
  try {
    await auth.acceptTerms(version);
    await router.push(safeNext(route.query["next"]));
  } catch (error) {
    problem.value = describe(error);
    // The words may have changed while they were being read: show the new ones.
    await load();
    agreed.value = false;
  } finally {
    busy.value = false;
  }
}

async function leave() {
  await auth.signOut();
  await router.push({ name: "sign-in" });
}

onMounted(load);
</script>

<template>
  <AuthCard
    title="Terms of use"
    subtitle="Read these before you use Blindspot. You are asked again if they change."
    wide
  >
    <StateView
      :state="state"
      title="Could not load the terms"
      :message="failure"
      action-label="Try again"
      @action="load"
    >
      <template v-if="terms">
        <v-alert v-if="problem" type="error" variant="tonal" class="mb-4" role="alert">
          {{ problem }}
        </v-alert>
        <v-alert type="warning" variant="tonal" class="mb-4" role="status">
          Blindspot sends real attacks. Use it only on systems you own or have written permission to
          test.
        </v-alert>
        <section v-for="section in terms.sections" :key="section.id" class="mb-4">
          <h2 class="text-h6 mb-1">{{ section.title }}</h2>
          <p v-for="(text, index) in section.paragraphs" :key="index" class="text-body-2 mb-2">
            {{ text }}
          </p>
        </section>
        <p class="text-caption text-medium-emphasis mb-2">Version {{ terms.version }}</p>
        <v-checkbox
          v-model="agreed"
          label="I have read these terms and I accept them"
          hide-details
        />
        <div class="d-flex flex-wrap ga-2 mt-4">
          <v-btn
            color="primary"
            size="large"
            :disabled="!agreed"
            :loading="busy"
            @click="accept(terms.version)"
          >
            Accept and continue
          </v-btn>
          <v-btn variant="text" :disabled="busy" @click="leave">Sign out</v-btn>
        </div>
      </template>
    </StateView>
  </AuthCard>
</template>

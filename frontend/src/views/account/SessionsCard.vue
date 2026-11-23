<script setup lang="ts">
import { mdiLaptop } from "@mdi/js";
import { onMounted, ref } from "vue";
import { api, describe } from "../../api/client";
import type { SessionInfo } from "../../api/types";
import StateView from "../../components/StateView.vue";
import { browserName, formatWhen } from "../../format";

const sessions = ref<SessionInfo[]>([]);
const state = ref<"loading" | "error" | "ready">("loading");
const failure = ref("");
const ending = ref("");

async function load() {
  state.value = "loading";
  try {
    sessions.value = await api<SessionInfo[]>("GET", "/api/auth/sessions");
    state.value = "ready";
  } catch (error) {
    failure.value = describe(error);
    state.value = "error";
  }
}

async function end(session: SessionInfo) {
  ending.value = session.id;
  try {
    await api("DELETE", `/api/auth/sessions/${session.id}`);
    sessions.value = sessions.value.filter((other) => other.id !== session.id);
  } catch (error) {
    failure.value = describe(error);
  } finally {
    ending.value = "";
  }
}

onMounted(load);
</script>

<template>
  <v-card border>
    <v-card-title tag="h2" class="text-h6">Where you are signed in</v-card-title>
    <v-card-text>
      <v-alert
        v-if="failure && state === 'ready'"
        type="error"
        variant="tonal"
        class="mb-4"
        role="alert"
      >
        {{ failure }}
      </v-alert>
      <StateView
        :state="state"
        title="Could not load your sessions"
        :message="failure"
        action-label="Try again"
        @action="load"
      >
        <v-list lines="two" class="pa-0">
          <v-list-item
            v-for="session in sessions"
            :key="session.id"
            :prepend-icon="mdiLaptop"
            :title="browserName(session.user_agent)"
            :subtitle="`${session.ip_address ?? 'Unknown address'} · last active ${formatWhen(session.last_seen_at)}`"
          >
            <template #append>
              <v-chip v-if="session.current" color="primary" size="small" label
                >This browser</v-chip
              >
              <v-btn
                v-else
                size="small"
                variant="text"
                color="error"
                :loading="ending === session.id"
                :aria-label="`Sign out ${browserName(session.user_agent)}`"
                @click="end(session)"
              >
                Sign out
              </v-btn>
            </template>
          </v-list-item>
        </v-list>
      </StateView>
    </v-card-text>
  </v-card>
</template>

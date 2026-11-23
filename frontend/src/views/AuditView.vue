<script setup lang="ts">
import { mdiHistory } from "@mdi/js";
import { computed, onMounted, reactive, ref } from "vue";
import { api, describe } from "../api/client";
import type { AuditEvent, AuditPage } from "../api/types";
import { AUDIT_ACTIONS, actionLabel, auditQuery, detailText, NO_FILTERS } from "../audit";
import PageHeader from "../components/PageHeader.vue";
import StateView from "../components/StateView.vue";
import { browserName, formatWhen } from "../format";

const events = ref<AuditEvent[]>([]);
const nextBefore = ref<string | null>(null);
const state = ref<"loading" | "error" | "ready">("loading");
const failure = ref("");
const loadingMore = ref(false);
const filters = reactive({ ...NO_FILTERS });

const actionItems = [
  { title: "Any action", value: "" },
  ...[...AUDIT_ACTIONS].map(([value, title]) => ({ title, value })),
];
const outcomeItems = [
  { title: "Any outcome", value: "" },
  { title: "Succeeded", value: "success" },
  { title: "Failed", value: "failure" },
];
const filtered = computed(() => Object.values(filters).some((value) => value !== ""));

// A newer search makes an older answer that arrives late meaningless, so it is dropped.
let latest = 0;
async function load() {
  const mine = ++latest;
  state.value = "loading";
  failure.value = "";
  try {
    const page = await api<AuditPage>("GET", `/api/audit?${auditQuery(filters, null)}`);
    if (mine !== latest) return;
    events.value = page.items;
    nextBefore.value = page.next_before;
    state.value = "ready";
  } catch (error) {
    if (mine !== latest) return;
    failure.value = describe(error);
    state.value = "error";
  }
}

async function more(before: string) {
  const mine = latest;
  loadingMore.value = true;
  try {
    const page = await api<AuditPage>("GET", `/api/audit?${auditQuery(filters, before)}`);
    if (mine !== latest) return;
    events.value = [...events.value, ...page.items];
    nextBefore.value = page.next_before;
  } catch (error) {
    if (mine === latest) failure.value = describe(error);
  } finally {
    loadingMore.value = false;
  }
}

function clear() {
  Object.assign(filters, NO_FILTERS);
  void load();
}

function line(event: AuditEvent): string {
  return [
    event.actor_name ?? "Nobody signed in",
    formatWhen(event.created_at),
    event.ip_address,
    event.user_agent === null ? null : browserName(event.user_agent),
  ]
    .filter((part) => part !== null)
    .join(" · ");
}

onMounted(load);
</script>

<template>
  <v-container>
    <PageHeader
      title="Audit log"
      subtitle="Who did what, newest first. Entries cannot be changed or deleted here."
    />

    <v-card border class="mb-4">
      <v-card-text>
        <v-form class="bs-filters" @submit.prevent="load">
          <v-autocomplete
            v-model="filters.action"
            :items="actionItems"
            label="Action"
            hide-details
          />
          <v-select v-model="filters.outcome" :items="outcomeItems" label="Outcome" hide-details />
          <v-text-field v-model="filters.actor" label="Username" autocomplete="off" hide-details />
          <v-text-field v-model="filters.since" label="Since" type="date" hide-details />
          <div class="bs-filter-buttons">
            <v-btn type="submit" color="primary">Apply filters</v-btn>
            <v-btn v-if="filtered" variant="text" @click="clear">Clear</v-btn>
          </div>
        </v-form>
      </v-card-text>
    </v-card>

    <StateView
      :state="state === 'ready' && events.length === 0 ? 'empty' : state"
      :title="state === 'error' ? 'Could not load the audit log' : 'Nothing matches'"
      :message="
        state === 'error'
          ? failure
          : filtered
            ? 'No events match these filters. Clear them to see everything.'
            : 'Nothing has been recorded yet.'
      "
      :action-label="state === 'error' ? 'Try again' : filtered ? 'Clear the filters' : undefined"
      @action="state === 'error' ? load() : clear()"
    >
      <v-card border>
        <v-list lines="three" class="pa-0" aria-label="Audit events">
          <v-list-item
            v-for="event in events"
            :key="event.id"
            :prepend-icon="mdiHistory"
            :title="actionLabel(event.action)"
          >
            <v-list-item-subtitle>{{ line(event) }}</v-list-item-subtitle>
            <v-list-item-subtitle v-if="detailText(event.detail)">
              {{ detailText(event.detail) }}
            </v-list-item-subtitle>
            <template #append>
              <v-chip
                size="small"
                label
                :color="event.outcome === 'success' ? 'success' : 'error'"
                variant="tonal"
              >
                {{ event.outcome === "success" ? "succeeded" : "failed" }}
              </v-chip>
            </template>
          </v-list-item>
        </v-list>
      </v-card>
      <v-alert v-if="failure" type="error" variant="tonal" class="mt-4" role="alert">
        {{ failure }}
      </v-alert>
      <div v-if="nextBefore !== null" class="text-center mt-4">
        <v-btn variant="tonal" :loading="loadingMore" @click="more(nextBefore)"
          >Show older events</v-btn
        >
      </div>
    </StateView>
  </v-container>
</template>

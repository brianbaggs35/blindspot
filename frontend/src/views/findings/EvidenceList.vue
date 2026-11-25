<script setup lang="ts">
import { mdiDeleteOutline, mdiEyeOutline, mdiLockOutline, mdiLockOpenOutline } from "@mdi/js";
import { ref } from "vue";
import { api, describe } from "../../api/client";
import type { FindingEvidence } from "../../api/types";

// The evidence of a finding. What is sealed shows as a mask until an administrator reveals it
// (written to the audit trail); a screenshot that is not sealed shows as the image.
const props = defineProps<{
  pentestId: string;
  findingId: string;
  evidence: FindingEvidence[];
  canEdit: boolean;
  canReveal: boolean;
}>();
const emit = defineEmits<{ changed: [message: string] }>();

const base = () => `/api/pentests/${props.pentestId}/findings/${props.findingId}/evidence`;
const revealed = ref(new Map<string, string>());
const failure = ref("");

async function reveal(one: FindingEvidence) {
  failure.value = "";
  try {
    const shown = await api<{ body: string }>("POST", `${base()}/${one.id}/reveal`);
    revealed.value = new Map(revealed.value).set(one.id, shown.body);
  } catch (error) {
    failure.value = describe(error);
  }
}

async function seal(one: FindingEvidence) {
  failure.value = "";
  try {
    await api("PATCH", `${base()}/${one.id}`, { sealed: !one.sealed });
    revealed.value = new Map([...revealed.value].filter(([key]) => key !== one.id));
    emit("changed", one.sealed ? "Unsealed." : "Sealed.");
  } catch (error) {
    failure.value = describe(error);
  }
}

async function remove(one: FindingEvidence) {
  failure.value = "";
  try {
    await api("DELETE", `${base()}/${one.id}`);
    emit("changed", "Evidence removed.");
  } catch (error) {
    failure.value = describe(error);
  }
}

const picture = (one: FindingEvidence) => {
  const shown = revealed.value.get(one.id);
  return shown === undefined
    ? `${base()}/${one.id}/image`
    : `data:${one.mime ?? ""};base64,${shown}`;
};
</script>

<template>
  <section aria-label="Evidence">
    <v-alert v-if="failure" type="error" variant="tonal" class="mb-3" role="alert">
      {{ failure }}
    </v-alert>
    <p v-if="evidence.length === 0" class="text-body-2">No evidence yet.</p>
    <v-card v-for="one in evidence" :key="one.id" border class="mb-3" :aria-label="one.title">
      <v-card-item :title="one.title">
        <template #append>
          <v-chip v-if="one.sealed" size="small" label :prepend-icon="mdiLockOutline" class="me-2">
            Sealed
          </v-chip>
          <v-btn
            v-if="one.sealed && canReveal && one.kind !== 'result' && !revealed.has(one.id)"
            size="small"
            variant="tonal"
            :prepend-icon="mdiEyeOutline"
            @click="reveal(one)"
          >
            Reveal
          </v-btn>
          <template v-if="canEdit">
            <v-btn
              v-if="one.kind !== 'result'"
              icon
              size="small"
              variant="text"
              :aria-label="one.sealed ? `Unseal ${one.title}` : `Seal ${one.title}`"
              @click="seal(one)"
            >
              <v-icon :icon="one.sealed ? mdiLockOpenOutline : mdiLockOutline" />
            </v-btn>
            <v-btn
              icon
              size="small"
              variant="text"
              color="error"
              :aria-label="`Remove ${one.title}`"
              @click="remove(one)"
            >
              <v-icon :icon="mdiDeleteOutline" />
            </v-btn>
          </template>
        </template>
      </v-card-item>
      <v-card-text>
        <router-link
          v-if="one.kind === 'result' && one.result_id"
          :to="{ name: 'pentest-result', params: { id: pentestId, rid: one.result_id } }"
        >
          {{ one.result_title ?? "The result" }}
        </router-link>
        <template v-else-if="one.kind === 'screenshot'">
          <img
            v-if="!one.sealed || revealed.has(one.id)"
            :src="picture(one)"
            :alt="one.title"
            class="bs-shot"
          />
          <p v-else class="text-body-2">The screenshot is sealed.</p>
        </template>
        <pre v-else class="bs-evidence">{{ revealed.get(one.id) ?? one.body }}</pre>
      </v-card-text>
    </v-card>
  </section>
</template>

<style scoped>
.bs-evidence {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.bs-shot {
  max-inline-size: 100%;
  border: 1px solid rgb(var(--v-theme-on-surface), 0.2);
  border-radius: 4px;
}
</style>

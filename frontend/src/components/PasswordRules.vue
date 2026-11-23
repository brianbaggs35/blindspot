<script setup lang="ts">
import { mdiCheckCircle, mdiCircleOutline } from "@mdi/js";
import { computed } from "vue";
import { passwordRules } from "../passwords";

const props = defineProps<{ password: string; username: string }>();
const rules = computed(() => passwordRules(props.password, props.username));
</script>

<template>
  <ul class="bs-rules text-body-2" aria-label="Password rules">
    <li v-for="rule in rules" :key="rule.id" :class="{ 'text-success': rule.met }">
      <v-icon
        :icon="rule.met ? mdiCheckCircle : mdiCircleOutline"
        size="small"
        aria-hidden="true"
      />
      {{ rule.text }}
      <span class="sr-only">{{ rule.met ? "(done)" : "(not yet)" }}</span>
    </li>
  </ul>
</template>

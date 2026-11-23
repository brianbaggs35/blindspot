<script setup lang="ts">
import { useRouter } from "vue-router";
import PageHeader from "../components/PageHeader.vue";
import StateView from "../components/StateView.vue";

const router = useRouter();
</script>

<template>
  <v-container>
    <PageHeader title="Page not found" />
    <StateView
      state="empty"
      title="Nothing is at this address"
      message="The address may be wrong, or the page may have moved."
      action-label="Back to the overview"
      @action="router.push('/')"
    />
  </v-container>
</template>

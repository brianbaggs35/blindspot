<script setup lang="ts">
import { useRouter } from "vue-router";
import PageHeader from "../components/PageHeader.vue";
import StateView from "../components/StateView.vue";

const router = useRouter();
</script>

<template>
  <v-container>
    <PageHeader title="No access" />
    <StateView
      state="empty"
      title="This page is for administrators"
      message="Your account can look at results but not manage Blindspot itself. Ask an administrator if you need more."
      action-label="Back to the overview"
      @action="router.push('/')"
    />
  </v-container>
</template>

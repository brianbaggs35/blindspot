<script setup lang="ts">
import { mdiRadar } from "@mdi/js";
import PageHeader from "../components/PageHeader.vue";
</script>

<template>
  <v-container fluid>
    <PageHeader title="Overview" subtitle="Everything Blindspot knows, in one place." />
    <v-row>
      <v-col cols="12" md="8" lg="6">
        <v-card class="pa-6" variant="tonal" color="primary">
          <v-card-title tag="h2" class="d-flex align-center ga-3 text-h6">
            <v-icon :icon="mdiRadar" aria-hidden="true" />
            Find what you cannot see
          </v-card-title>
          <v-card-text>
            Blindspot is being built. Only run it against systems you own or have written permission
            to test.
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

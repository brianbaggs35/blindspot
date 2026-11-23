<script setup lang="ts">
import { mdiRadar } from "@mdi/js";
</script>

<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" md="8" lg="6">
        <v-card class="pa-6" variant="tonal" color="primary">
          <v-card-title tag="h1" class="d-flex align-center ga-3 text-h5">
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

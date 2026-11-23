<script setup lang="ts">
// The card that sign-in and setup sit in, over the page without a menu.
defineProps<{ title: string; subtitle?: string }>();
</script>

<template>
  <v-container class="bs-auth">
    <v-card class="bs-auth-card pa-4 pa-sm-6" border>
      <header class="text-center mb-4">
        <img src="/logo-mark.svg" alt="" width="56" height="56" />
        <h1 class="text-h5 font-weight-bold mt-2">{{ title }}</h1>
        <p v-if="subtitle" class="text-body-2 text-medium-emphasis mt-1">{{ subtitle }}</p>
      </header>
      <slot />
    </v-card>
  </v-container>
</template>

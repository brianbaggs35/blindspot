<script setup lang="ts">
// The permission warning, in one place so it says the same thing wherever people act: when they
// create a pentest, change what is in scope, confirm permission and press Start.
</script>

<template>
  <v-alert
    type="warning"
    variant="tonal"
    role="status"
    density="compact"
    title="Only test what you are allowed to test"
  >
    Blindspot sends real attacks. Use it only on systems you own or have written permission to test.
    Testing without permission can be a crime, and you are responsible for what you run.
  </v-alert>
</template>

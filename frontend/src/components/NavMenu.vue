<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import { navSections } from "../navigation";
import { useAuthStore } from "../stores/auth";

defineProps<{ rail: boolean }>();

// Tapping the page you are already on changes no route, so the menu is told directly.
defineEmits<{ navigate: [] }>();

const router = useRouter();
const auth = useAuthStore();
const sections = computed(() => navSections(router, auth.isAdmin));
</script>

<template>
  <nav aria-label="Main">
    <template v-for="(section, index) in sections" :key="section.id">
      <v-divider v-if="index > 0 && rail" class="my-2" />
      <h2 v-else-if="!rail" :id="`nav-${section.id}`" class="bs-nav-heading px-4 pt-3 pb-1">
        {{ section.title }}
      </h2>
      <v-list nav density="comfortable" role="presentation" tabindex="-1">
        <v-list-item
          v-for="item in section.items"
          :key="item.to"
          :to="item.to"
          :prepend-icon="item.icon"
          :title="item.label"
          rounded="lg"
          color="primary"
          @click="$emit('navigate')"
        >
          <v-tooltip v-if="rail" activator="parent" location="end">{{ item.label }}</v-tooltip>
        </v-list-item>
      </v-list>
    </template>
  </nav>
</template>

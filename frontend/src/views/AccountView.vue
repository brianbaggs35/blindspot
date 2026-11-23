<script setup lang="ts">
import PageHeader from "../components/PageHeader.vue";
import { formatWhen } from "../format";
import { useAuthStore } from "../stores/auth";
import ChangePasswordCard from "./account/ChangePasswordCard.vue";
import PasskeysCard from "./account/PasskeysCard.vue";
import SessionsCard from "./account/SessionsCard.vue";

const auth = useAuthStore();
</script>

<template>
  <v-container fluid>
    <PageHeader title="Account" subtitle="Your sign-in details, passkeys and browsers." />
    <v-row v-if="auth.user">
      <v-col cols="12" lg="4">
        <v-card border>
          <v-card-title tag="h2" class="text-h6">{{ auth.user.display_name }}</v-card-title>
          <v-card-text>
            <dl class="bs-facts">
              <dt>Username</dt>
              <dd class="mono">{{ auth.user.username }}</dd>
              <dt>Role</dt>
              <dd>
                <v-chip size="small" label :color="auth.isAdmin ? 'primary' : undefined">
                  {{ auth.user.role }}
                </v-chip>
                <span v-if="!auth.isAdmin" class="text-body-2 text-medium-emphasis ml-2">
                  can look, not change
                </span>
              </dd>
              <dt>Last sign-in</dt>
              <dd>{{ formatWhen(auth.user.last_sign_in_at) }}</dd>
            </dl>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" lg="8">
        <v-row>
          <v-col cols="12"><ChangePasswordCard /></v-col>
          <v-col cols="12"><PasskeysCard /></v-col>
          <v-col cols="12"><SessionsCard /></v-col>
        </v-row>
      </v-col>
    </v-row>
  </v-container>
</template>

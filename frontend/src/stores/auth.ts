import { defineStore } from "pinia";
import { api } from "../api/client";
import type { Status, Terms, User } from "../api/types";
import { signInWithPasskey } from "../passkeys";

export interface SetupDetails {
  setup_code: string;
  username: string;
  display_name: string;
  password: string;
}

// Who is signed in, and whether the app still needs its first administrator. The router asks
// `load()` before every first page, so a screen never has to wonder.
export const useAuthStore = defineStore("auth", {
  state: () => ({
    loaded: false,
    setupRequired: false,
    user: null as User | null,
  }),
  getters: {
    isSignedIn: (state) => state.user !== null,
    isAdmin: (state) => state.user?.role === "admin",
    /** Whether the signed-in person has accepted the terms of use as they are now. */
    termsAccepted: (state) => state.user?.terms_accepted === true,
  },
  actions: {
    /** Ask the API once; later calls reuse the answer unless `again` is given. */
    async load(again = false) {
      if (this.loaded && !again) return;
      try {
        const status = await api<Status>("GET", "/api/auth/status");
        this.setupRequired = status.setup_required;
        this.user = status.user;
      } catch {
        // The API is not answering: treat the person as signed out. Signing in says why.
        this.setupRequired = false;
        this.user = null;
      }
      this.loaded = true;
    },
    async setup(details: SetupDetails) {
      this.user = await api<User>("POST", "/api/auth/setup", details);
      this.setupRequired = false;
    },
    async signIn(username: string, password: string) {
      this.user = await api<User>("POST", "/api/auth/login", { username, password });
    },
    async signInWithPasskey() {
      this.user = await signInWithPasskey();
    },
    async signOut() {
      try {
        await api("POST", "/api/auth/logout");
      } catch {
        // Best effort: if the server cannot be reached the person is still signed out here, and
        // the session there ends on its own when it expires.
      }
      this.user = null;
    },
    /** Record that the person read and accepted this version of the terms. */
    async acceptTerms(version: string) {
      await api<Terms>("POST", "/api/terms/accept", { version });
      if (this.user) this.user = { ...this.user, terms_accepted: true };
    },
    /** The session ended on the server (expired, revoked, account turned off). */
    sessionEnded() {
      this.user = null;
    },
  },
});

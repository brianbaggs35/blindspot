import type { RouteLocationNormalized, RouteLocationRaw } from "vue-router";
import { useAuthStore } from "../stores/auth";

/** Where to go after signing in: only a path inside this app, never another site. */
export function safeNext(raw: unknown): string {
  return typeof raw === "string" && /^\/(?![/\\])/.test(raw) ? raw : "/";
}

// Runs before every navigation. The order matters: setup comes first (nothing else works until
// there is an administrator), then who is signed in, then the terms of use, then what they may open.
export async function guard(to: RouteLocationNormalized): Promise<true | RouteLocationRaw> {
  const auth = useAuthStore();
  await auth.load();
  if (auth.setupRequired) return to.name === "setup" ? true : { name: "setup" };
  if (to.name === "setup") return { path: "/" };
  if (!auth.isSignedIn) {
    if ((to.meta.access ?? "user") === "public") return true;
    return { name: "sign-in", query: { next: to.fullPath } };
  }
  if (to.name === "sign-in") return { path: safeNext(to.query["next"]) };
  // Nothing in the app opens until the terms of use are accepted; they are asked for again when
  // their text changes.
  if (!auth.termsAccepted) {
    return to.name === "terms" ? true : { name: "terms", query: { next: to.fullPath } };
  }
  if (to.name === "terms") return { path: safeNext(to.query["next"]) };
  if (to.meta.access === "admin" && !auth.isAdmin) return { name: "forbidden" };
  return true;
}

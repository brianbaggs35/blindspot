import {
  mdiAccountCircleOutline,
  mdiAccountGroupOutline,
  mdiBrain,
  mdiClipboardListOutline,
  mdiHistory,
  mdiRadar,
  mdiRobotOutline,
  mdiTargetAccount,
  mdiToolboxOutline,
} from "@mdi/js";
import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { setSessionEndedHandler } from "../api/client";
import { pageTitle } from "../navigation";
import { useAuthStore } from "../stores/auth";
import { guard } from "./guard";

export const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "home",
    component: () => import("../views/HomeView.vue"),
    meta: { nav: { label: "Overview", group: "work", order: 10, icon: mdiRadar } },
  },
  {
    path: "/setup",
    name: "setup",
    component: () => import("../views/SetupView.vue"),
    meta: { title: "Set up Blindspot", access: "public", layout: "bare" },
  },
  {
    path: "/sign-in",
    name: "sign-in",
    component: () => import("../views/SignInView.vue"),
    meta: { title: "Sign in", access: "public", layout: "bare" },
  },
  {
    path: "/terms",
    name: "terms",
    component: () => import("../views/TermsView.vue"),
    meta: { title: "Terms of use", layout: "bare" },
  },
  {
    path: "/pentests",
    name: "pentests",
    component: () => import("../views/PentestsView.vue"),
    meta: {
      title: "Pentests",
      nav: { label: "Pentests", group: "work", order: 30, icon: mdiTargetAccount },
    },
  },
  {
    path: "/pentests/:id",
    name: "pentest",
    component: () => import("../views/PentestDetailView.vue"),
    meta: { title: "Pentest" },
  },
  {
    path: "/pentests/:id/checklist",
    name: "pentest-checklist",
    component: () => import("../views/PentestChecklistView.vue"),
    meta: { title: "Checklist" },
  },
  {
    path: "/pentests/:id/results",
    name: "pentest-results",
    component: () => import("../views/PentestResultsView.vue"),
    meta: { title: "Results" },
  },
  {
    path: "/pentests/:id/results/:rid",
    name: "pentest-result",
    component: () => import("../views/PentestResultView.vue"),
    meta: { title: "Result" },
  },
  {
    path: "/pentests/:id/findings",
    name: "pentest-findings",
    component: () => import("../views/PentestFindingsView.vue"),
    meta: { title: "Findings" },
  },
  {
    path: "/pentests/:id/findings/:fid",
    name: "pentest-finding",
    component: () => import("../views/PentestFindingView.vue"),
    meta: { title: "Finding" },
  },
  {
    path: "/pentests/:id/agents",
    name: "pentest-agents",
    component: () => import("../views/PentestAgentsView.vue"),
    meta: { title: "Agents" },
  },
  {
    path: "/agents",
    name: "agents",
    component: () => import("../views/AgentsView.vue"),
    meta: {
      title: "Agents",
      nav: { label: "Agents", group: "work", order: 40, icon: mdiRobotOutline },
    },
  },
  {
    path: "/methodologies",
    name: "methodologies",
    component: () => import("../views/MethodologiesView.vue"),
    meta: {
      title: "Methodologies",
      nav: { label: "Methodologies", group: "work", order: 50, icon: mdiClipboardListOutline },
    },
  },
  {
    path: "/ai-providers",
    name: "ai-providers",
    component: () => import("../views/AiProvidersView.vue"),
    meta: {
      title: "AI providers",
      nav: { label: "AI providers", group: "system", order: 30, icon: mdiBrain },
    },
  },
  {
    path: "/tools",
    name: "tools",
    component: () => import("../views/ToolsView.vue"),
    meta: {
      title: "Tools",
      nav: { label: "Tools", group: "system", order: 20, icon: mdiToolboxOutline },
    },
  },
  {
    path: "/users",
    name: "users",
    component: () => import("../views/UsersView.vue"),
    meta: {
      title: "Users",
      access: "admin",
      nav: { label: "Users", group: "system", order: 60, icon: mdiAccountGroupOutline },
    },
  },
  {
    path: "/audit",
    name: "audit",
    component: () => import("../views/AuditView.vue"),
    meta: {
      title: "Audit log",
      access: "admin",
      nav: { label: "Audit log", group: "system", order: 70, icon: mdiHistory },
    },
  },
  {
    path: "/account",
    name: "account",
    component: () => import("../views/AccountView.vue"),
    meta: {
      title: "Account",
      nav: { label: "Account", group: "system", order: 90, icon: mdiAccountCircleOutline },
    },
  },
  {
    path: "/forbidden",
    name: "forbidden",
    component: () => import("../views/ForbiddenView.vue"),
    meta: { title: "No access" },
  },
  {
    path: "/:pathMatch(.*)*",
    name: "not-found",
    component: () => import("../views/NotFoundView.vue"),
    meta: { title: "Page not found" },
  },
];

export function createBlindspotRouter(history = createWebHistory()) {
  const router = createRouter({ history, routes });
  router.beforeEach(guard);
  router.afterEach((to) => {
    document.title = pageTitle(to.meta.title);
  });
  // A session that ends while a page is open (it expired, or an administrator ended it) sends the
  // person to sign in again, and back to this page afterwards.
  setSessionEndedHandler(() => {
    const auth = useAuthStore();
    if (!auth.isSignedIn) return;
    auth.sessionEnded();
    void router.push({ name: "sign-in", query: { next: router.currentRoute.value.fullPath } });
  });
  return router;
}

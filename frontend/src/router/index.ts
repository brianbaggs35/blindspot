import { mdiRadar } from "@mdi/js";
import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { pageTitle } from "../navigation";

export const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "home",
    component: () => import("../views/HomeView.vue"),
    meta: { nav: { label: "Overview", group: "work", order: 10, icon: mdiRadar } },
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
  router.afterEach((to) => {
    document.title = pageTitle(to.meta.title);
  });
  return router;
}

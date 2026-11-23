import { createRouter, createWebHistory } from "vue-router";

export const routes = [
  {
    path: "/",
    name: "home",
    component: () => import("../views/HomeView.vue"),
  },
];

export function createBlindspotRouter(history = createWebHistory()) {
  return createRouter({ history, routes });
}

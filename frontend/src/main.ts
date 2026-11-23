import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono/400.css";
import { createPinia } from "pinia";
import { createApp } from "vue";
import "vuetify/styles";
import "./styles/main.css";
import App from "./App.vue";
import { createBlindspotVuetify } from "./plugins/vuetify";
import { createBlindspotRouter } from "./router";
import { systemTheme } from "./stores/theme";

createApp(App)
  .use(createPinia())
  .use(createBlindspotRouter())
  .use(createBlindspotVuetify(systemTheme()))
  .mount("#app");

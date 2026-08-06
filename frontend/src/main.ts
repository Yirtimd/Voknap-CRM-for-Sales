import { createApp } from "vue";

import App from "./App.vue";
import { router } from "./router";
import "./design-system/theme";
import "./design-system/tokens.css";
import "./style.css";
import "./design-system/dark-theme.css";
import { crmStore } from "./stores/crm";

async function bootstrap() {
  await crmStore.refreshSession();
  createApp(App).use(router).mount("#app");
}

void bootstrap();

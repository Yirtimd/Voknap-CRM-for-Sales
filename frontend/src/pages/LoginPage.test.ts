import { mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { describe, expect, it } from "vitest";

import LoginPage from "./LoginPage.vue";
import { crmStore } from "../stores/crm";

describe("LoginPage", () => {
  it("switches between login and registration without competing forms", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/", component: { template: "<div />" } }]
    });
    await router.push("/");
    await router.isReady();

    const wrapper = mount(LoginPage, {
      global: { plugins: [router] }
    });

    expect(wrapper.get("h1").text()).toBe("Продажи, которые двигаются сами");
    expect(wrapper.findAll("form")).toHaveLength(1);
    expect(wrapper.text()).toContain("Войти");
    await wrapper.get(".auth-switch button:last-child").trigger("click");
    expect(wrapper.findAll("form")).toHaveLength(1);
    expect(wrapper.text()).toContain("Создание компании");
    expect(wrapper.text()).toContain("Создать рабочее пространство");
    wrapper.unmount();
  });

  it("shows a separate MFA challenge after password verification", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/", component: { template: "<div />" } }]
    });
    await router.push("/");
    await router.isReady();
    crmStore.mfaToken.value = "mfa-token";

    const wrapper = mount(LoginPage, { global: { plugins: [router] } });

    expect(wrapper.text()).toContain("Подтверждение входа");
    expect(wrapper.text()).toContain("recovery-код");
    expect(wrapper.findAll("form")).toHaveLength(1);
    wrapper.unmount();
    crmStore.mfaToken.value = "";
  });
});

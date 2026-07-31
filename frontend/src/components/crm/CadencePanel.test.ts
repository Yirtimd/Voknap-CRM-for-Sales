import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { crmStore } from "../../stores/crm";
import { sequenceStore } from "../../stores/sequences";
import CadencePanel from "./CadencePanel.vue";

beforeEach(() => {
  crmStore.me.value = {
    user_id: "user-1",
    email: "owner@example.test",
    full_name: "Owner",
    tenant_id: "tenant-1",
    role: "owner",
    permissions: ["crm:read", "crm:write", "sales:manage"]
  };
  sequenceStore.cadences.value = [{
    id: "cadence-1",
    name: "B2B follow-up",
    description: null,
    is_active: true,
    steps: [{ id: "step-1", position: 0, step_type: "call", delay_minutes: 0, title: "Позвонить", body: null, task_priority: "high" }],
    version: 1,
    created_by_id: "user-1",
    updated_by_id: "user-1",
    created_at: "2026-07-31T00:00:00Z",
    updated_at: "2026-07-31T00:00:00Z"
  }];
  sequenceStore.enrollments.value = [{
    id: "enrollment-1",
    cadence_id: "cadence-1",
    cadence_name: "B2B follow-up",
    contact_id: "contact-1",
    contact_name: "Ирина Покупатель",
    company_id: "company-1",
    deal_id: null,
    connector_account_id: null,
    owner_id: "user-1",
    status: "active",
    current_step: 0,
    step_count: 1,
    next_run_at: "2026-07-31T12:00:00Z",
    last_executed_at: null,
    stop_reason: null,
    version: 1,
    created_at: "2026-07-31T00:00:00Z",
    updated_at: "2026-07-31T00:00:00Z"
  }];
  vi.spyOn(sequenceStore, "refresh").mockResolvedValue();
});

afterEach(() => vi.restoreAllMocks());

describe("CadencePanel", () => {
  it("keeps sequences linked to contacts and exposes lifecycle controls", async () => {
    const wrapper = mount(CadencePanel, {
      props: {
        companyId: "company-1",
        contacts: [{
          id: "contact-1",
          company_id: "company-1",
          name: "Ирина Покупатель",
          phone: "+79990000000",
          email: "buyer@example.com",
          company_name: "Компания",
          is_archived: false,
          deleted_at: null,
          version: 1
        }],
        deals: []
      }
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Sequences и cadences");
    expect(wrapper.text()).toContain("Ирина Покупатель");
    expect(wrapper.text()).toContain("B2B follow-up");
    expect(wrapper.text()).toContain("Пауза");
    expect(wrapper.text()).toContain("Стоп");
    expect(wrapper.text()).toContain("Новая cadence");
  });
});

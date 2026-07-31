import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { crmStore } from "../../stores/crm";
import { lifecycleStore } from "../../stores/lifecycle";
import type { Lead } from "../../types";
import EntityCrudDrawer from "./EntityCrudDrawer.vue";

const lead: Lead = {
  id: "lead-1",
  company_id: "company-1",
  title: "Новый запрос",
  source: "site",
  status: "new",
  contact_id: null,
  owner_id: "user-1",
  score: 78,
  score_grade: "hot",
  score_model_version: "rules-v1",
  score_factors: [
    {
      key: "source",
      label: "Качество источника",
      points: 20,
      max_points: 20,
      signal: "referral"
    }
  ],
  is_archived: false,
  deleted_at: null,
  version: 3
};

beforeEach(() => {
  crmStore.me.value = {
    user_id: "user-1",
    email: "rep@example.test",
    full_name: "Менеджер",
    tenant_id: "tenant-1",
    role: "sales_rep",
    permissions: ["crm:read", "crm:write"]
  };
  crmStore.companies.value = [{
    id: "company-1",
    name: "Компания",
    website: null,
    industry: null,
    description: null,
    status: "active",
    company_type: null,
    client_since: null,
    created_at: "2026-01-01T00:00:00Z"
  }];
  crmStore.leads.value = [lead];
});

afterEach(() => vi.restoreAllMocks());

describe("EntityCrudDrawer", () => {
  it("shows record CRUD and lead lifecycle actions inside the familiar page drawer", async () => {
    const wrapper = mount(EntityCrudDrawer, {
      props: { entityType: "leads", record: lead },
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } }
    });

    expect(wrapper.text()).toContain("Редактировать");
    expect(wrapper.text()).toContain("История");
    expect(wrapper.text()).toContain("В архив");
    expect(wrapper.text()).toContain("В корзину");
    expect(wrapper.text()).toContain("Квалифицировать");
    expect(wrapper.text()).toContain("Дисквалифицировать");
  });

  it("renders a create form with context defaults", async () => {
    const wrapper = mount(EntityCrudDrawer, {
      props: { entityType: "contacts", initialMode: "create", initialValues: { company_id: "company-1" } },
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } }
    });
    await flushPromises();

    expect(wrapper.get("form").element.tagName).toBe("FORM");
    expect(wrapper.text()).toContain("Новый контакт");
    expect(wrapper.get('select').element.value).toBe("company-1");
    expect(wrapper.text()).toContain("Создать");
  });

  it("shows explainable lead score factors", async () => {
    const wrapper = mount(EntityCrudDrawer, {
      props: { entityType: "leads", record: lead },
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } }
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Lead score");
    expect(wrapper.text()).toContain("78/100");
    expect(wrapper.text()).toContain("Качество источника");
    expect(wrapper.text()).toContain("+20/20");
  });

  it("shows only duplicate candidates returned by backend", async () => {
    const candidate = { ...lead, id: "lead-2", title: "Запрос с сайта", version: 2 };
    lifecycleStore.duplicateCandidates.value = [{
      id: "duplicate-1",
      entity_type: "leads",
      record_a_id: lead.id,
      record_b_id: candidate.id,
      score: 92,
      matched_fields: ["title", "contact_id"],
      status: "open",
      version: 1,
      detected_at: "2026-07-24T00:00:00Z",
      resolved_at: null
    }];
    vi.spyOn(lifecycleStore, "loadDuplicateCandidates").mockResolvedValue();
    vi.spyOn(lifecycleStore, "loadDuplicateRecord").mockResolvedValue(candidate);

    const wrapper = mount(EntityCrudDrawer, {
      props: { entityType: "leads", record: lead },
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } }
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Запрос с сайта");
    expect(wrapper.text()).toContain("Совпадение 92%");
    expect(wrapper.text()).toContain("title, contact_id");
  });
});

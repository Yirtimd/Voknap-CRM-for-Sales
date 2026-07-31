import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Cadence, CadenceEnrollment } from "../types";
import { crmStore } from "./crm";
import { sequenceStore } from "./sequences";

function response(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: vi.fn().mockResolvedValue(data),
    text: vi.fn().mockResolvedValue(JSON.stringify(data))
  };
}

const cadence: Cadence = {
  id: "cadence-1",
  name: "Follow-up",
  description: null,
  is_active: true,
  steps: [{
    id: "step-1",
    position: 0,
    step_type: "manual_email",
    delay_minutes: 0,
    title: "Написать клиенту",
    body: "Здравствуйте",
    task_priority: "high"
  }],
  version: 1,
  created_by_id: "user-1",
  updated_by_id: "user-1",
  created_at: "2026-07-31T00:00:00Z",
  updated_at: "2026-07-31T00:00:00Z"
};

const enrollment: CadenceEnrollment = {
  id: "enrollment-1",
  cadence_id: cadence.id,
  cadence_name: cadence.name,
  contact_id: "contact-1",
  contact_name: "Покупатель",
  company_id: "company-1",
  deal_id: null,
  connector_account_id: null,
  owner_id: "user-1",
  status: "active",
  current_step: 0,
  step_count: 1,
  next_run_at: "2026-07-31T00:00:00Z",
  last_executed_at: null,
  stop_reason: null,
  version: 1,
  created_at: "2026-07-31T00:00:00Z",
  updated_at: "2026-07-31T00:00:00Z"
};

beforeEach(() => {
  crmStore.token.value = "token-1";
  crmStore.tenantId.value = "tenant-1";
  crmStore.me.value = {
    user_id: "user-1",
    email: "owner@example.test",
    full_name: "Owner",
    tenant_id: "tenant-1",
    role: "owner",
    permissions: ["crm:read", "crm:write", "sales:manage"]
  };
  sequenceStore.cadences.value = [];
  sequenceStore.enrollments.value = [];
  sequenceStore.executions.value = {};
  sequenceStore.emailAccounts.value = [];
  vi.spyOn(crmStore, "refreshAll").mockResolvedValue();
  vi.spyOn(crmStore, "loadCompanyWorkspace").mockResolvedValue();
});

afterEach(() => vi.unstubAllGlobals());

describe("sequence store", () => {
  it("loads cadences, company enrollments and safe email account options", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response([cadence]))
      .mockResolvedValueOnce(response([enrollment]))
      .mockResolvedValueOnce(response([{ id: "email-1", title: "Sales", status: "connected" }]));
    vi.stubGlobal("fetch", fetchMock);

    await sequenceStore.refresh("company-1");

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/sequences",
      "/api/sequences/enrollments?company_id=company-1",
      "/api/sequences/email-accounts"
    ]);
    expect(sequenceStore.enrollments.value[0].contact_name).toBe("Покупатель");
    expect(sequenceStore.emailAccounts.value[0].title).toBe("Sales");
  });

  it("sends optimistic version for pause", async () => {
    const paused = { ...enrollment, status: "paused", version: 2 };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(paused))
      .mockResolvedValueOnce(response([cadence]))
      .mockResolvedValueOnce(response([paused]))
      .mockResolvedValueOnce(response([]));
    vi.stubGlobal("fetch", fetchMock);

    await sequenceStore.act(enrollment, "pause", "company-1", "На паузе");

    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({
      version: 1,
      reason: "На паузе"
    });
    expect(sequenceStore.enrollments.value[0].status).toBe("paused");
  });
});

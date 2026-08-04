import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { crmStore } from "./crm";
import { customFieldsStore } from "./customFields";

function response(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: vi.fn().mockResolvedValue(data),
    text: vi.fn().mockResolvedValue(JSON.stringify(data))
  };
}

const definition = {
  id: "field-1",
  entity_type: "deals" as const,
  code: "segment",
  label: "Сегмент",
  description: null,
  field_type: "select" as const,
  options: ["Enterprise", "SMB"],
  is_required: false,
  is_filterable: true,
  is_reportable: true,
  is_active: true,
  sort_order: 100,
  version: 1,
  created_at: "2026-08-04T12:00:00Z",
  updated_at: "2026-08-04T12:00:00Z"
};

beforeEach(() => {
  crmStore.token.value = "token-1";
  crmStore.tenantId.value = "tenant-1";
  customFieldsStore.definitions.value.deals = [];
});

afterEach(() => vi.unstubAllGlobals());

describe("custom field store", () => {
  it("loads schema and applies a server-side filter", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response([definition]))
      .mockResolvedValueOnce(response({ entity_ids: ["deal-1"], matched: 1 }));
    vi.stubGlobal("fetch", fetchMock);

    await customFieldsStore.loadDefinitions("deals");
    const ids = await customFieldsStore.search("deals", definition.id, "eq", "Enterprise");

    expect(customFieldsStore.definitions.value.deals[0].label).toBe("Сегмент");
    expect(ids).toEqual(["deal-1"]);
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/custom-fields/definitions?entity_type=deals&include_inactive=false",
      "/api/custom-fields/search/deals"
    ]);
  });

  it("sends value versions for optimistic locking", async () => {
    const saved = [{ field: definition, value: "SMB", version: 2, updated_at: "2026-08-04T12:01:00Z" }];
    const fetchMock = vi.fn().mockResolvedValue(response(saved));
    vi.stubGlobal("fetch", fetchMock);

    await customFieldsStore.saveValues("deals", "deal-1", [
      { field: definition, value: "SMB", version: 1, updated_at: null }
    ]);

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toEqual({
      values: [{ field_id: "field-1", value: "SMB", version: 1 }]
    });
  });
});

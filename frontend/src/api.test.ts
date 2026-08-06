import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, apiErrorMessage, apiPage, buildQuery, emptyToNull, post, setAuthRefreshHandler } from "./api";

afterEach(() => {
  setAuthRefreshHandler(null);
  vi.unstubAllGlobals();
});

describe("API client", () => {
  it("adds authentication and tenant headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: vi.fn().mockResolvedValue({ id: "user-1" })
    });
    vi.stubGlobal("fetch", fetchMock);

    await api("/me", {}, "token-1", "tenant-1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/me",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer token-1",
          "X-Tenant-Id": "tenant-1"
        })
      })
    );
  });

  it("refreshes an expired access token once and retries the request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 401 })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: vi.fn().mockResolvedValue({ id: "user-1" })
      });
    vi.stubGlobal("fetch", fetchMock);
    setAuthRefreshHandler(async () => "token-2");

    await expect(api<{ id: string }>("/me", {}, "token-1", "tenant-1")).resolves.toEqual({ id: "user-1" });

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/me",
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer token-2" }) })
    );
  });

  it("exposes API status, detail, and optimistic-lock version", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        text: vi.fn().mockResolvedValue('{"detail":{"message":"Version conflict","current_version":7}}')
      })
    );

    await expect(api("/sales/companies")).rejects.toMatchObject({
      name: "ApiError",
      status: 403,
      detail: { message: "Version conflict", current_version: 7 },
      currentVersion: 7
    });
  });

  it("reads server pagination headers and falls back when headers are absent", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          "X-Total-Count": "245",
          "X-Page": "2",
          "X-Page-Size": "25",
          "X-Total-Pages": "10"
        }),
        json: vi.fn().mockResolvedValue([{ id: "2" }])
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: vi.fn().mockResolvedValue([{ id: "1" }, { id: "2" }])
      });
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiPage<{ id: string }>("/sales/contacts")).resolves.toMatchObject({
      items: [{ id: "2" }],
      pagination: { page: 2, pageSize: 25, total: 245, totalPages: 10 }
    });
    await expect(apiPage<{ id: string }>("/sales/contacts", {}, undefined, undefined, { page: 3 })).resolves.toMatchObject({
      pagination: { page: 3, pageSize: 2, total: 2, totalPages: 1 }
    });
  });

  it("builds query values without losing existing parameters", () => {
    expect(buildQuery("/sales/leads?sort=created_at", {
      page: 2,
      status: "new",
      owner_id: null,
      tag: ["hot", "priority"]
    })).toBe("/sales/leads?sort=created_at&page=2&status=new&tag=hot&tag=priority");
  });

  it("forwards AbortSignal from RequestInit", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: vi.fn().mockResolvedValue({ id: "contact-1" })
    });
    vi.stubGlobal("fetch", fetchMock);

    await api("/sales/contacts", { signal: controller.signal });

    expect(fetchMock).toHaveBeenCalledWith("/api/sales/contacts", expect.objectContaining({ signal: controller.signal }));
  });

  it("normalizes form payloads", () => {
    expect(emptyToNull({ name: "Company", website: "" })).toEqual({
      name: "Company",
      website: null
    });
    expect(post({ title: "Deal" }, "PATCH")).toEqual({
      method: "PATCH",
      body: '{"title":"Deal"}'
    });
  });

  it("turns validation, permission, and version failures into actionable messages", () => {
    expect(apiErrorMessage(new ApiError(422, [
      { loc: ["body", "stages", 0, "code"], msg: "String should match pattern" }
    ]))).toContain("stages.0.code");
    expect(apiErrorMessage(new ApiError(403, "Forbidden"))).toBe("Недостаточно прав для этого действия.");
    expect(apiErrorMessage(new ApiError(409, { message: "Version conflict" }, 6))).toContain("Обновите объект");
  });
});

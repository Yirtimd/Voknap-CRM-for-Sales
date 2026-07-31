import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { NotificationItem } from "../types";
import { crmStore } from "./crm";
import { notificationStore } from "./notifications";

function response(data: unknown, status = 200, headers: Record<string, string> = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: vi.fn().mockResolvedValue(data),
    text: vi.fn().mockResolvedValue(status === 204 ? "" : JSON.stringify(data))
  };
}

const notification: NotificationItem = {
  id: "notification-1",
  category: "automation",
  priority: "high",
  title: "Проверьте сделку",
  body: "Сценарий обнаружил риск",
  link: "/deals?deal=deal-1",
  source_type: "automation_run",
  source_id: "run-1",
  metadata: {},
  read_at: null,
  created_at: "2026-07-31T12:00:00Z"
};

beforeEach(() => {
  crmStore.token.value = "token-1";
  crmStore.tenantId.value = "tenant-1";
  notificationStore.recent.value = [];
  notificationStore.items.value = [];
  notificationStore.summary.value = { unread_count: 0, critical_count: 0 };
});

afterEach(() => vi.unstubAllGlobals());

describe("notification store", () => {
  it("loads personal unread count and bell items", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ unread_count: 1, critical_count: 0 }))
      .mockResolvedValueOnce(response([notification], 200, {
        "X-Total-Count": "1",
        "X-Page": "1",
        "X-Page-Size": "10",
        "X-Total-Pages": "1"
      }));
    vi.stubGlobal("fetch", fetchMock);

    await notificationStore.refreshRecent();

    expect(notificationStore.summary.value.unread_count).toBe(1);
    expect(notificationStore.recent.value[0].title).toBe("Проверьте сделку");
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/notifications/summary",
      "/api/notifications?unread_only=true&page=1&page_size=10"
    ]);
  });

  it("clears bell state after read all", async () => {
    notificationStore.recent.value = [notification];
    notificationStore.items.value = [notification];
    notificationStore.summary.value = { unread_count: 1, critical_count: 0 };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(undefined, 204, { "content-length": "0" })));

    await notificationStore.readAll();

    expect(notificationStore.summary.value.unread_count).toBe(0);
    expect(notificationStore.recent.value).toEqual([]);
    expect(notificationStore.items.value[0].read_at).not.toBeNull();
  });
});

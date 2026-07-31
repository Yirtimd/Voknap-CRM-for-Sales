import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { notificationStore } from "../../stores/notifications";
import NotificationBell from "./NotificationBell.vue";

const push = vi.fn();
vi.mock("vue-router", () => ({ useRouter: () => ({ push }) }));

beforeEach(() => {
  notificationStore.summary.value = { unread_count: 1, critical_count: 0 };
  notificationStore.recent.value = [{
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
  }];
  vi.spyOn(notificationStore, "refreshRecent").mockResolvedValue();
  vi.spyOn(notificationStore, "setRead").mockImplementation(async (item) => ({ ...item, read_at: "2026-07-31T12:01:00Z" }));
});

afterEach(() => {
  vi.restoreAllMocks();
  push.mockReset();
});

describe("NotificationBell", () => {
  it("shows unread events and opens their CRM object", async () => {
    const wrapper = mount(NotificationBell);
    await wrapper.get('button[aria-label="Уведомления"]').trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Проверьте сделку");
    await wrapper.get(".notification-bell__row").trigger("click");
    await flushPromises();

    expect(notificationStore.setRead).toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith("/deals?deal=deal-1");
    wrapper.unmount();
  });
});

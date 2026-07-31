import { ref } from "vue";

import { api, apiPage, buildQuery, post } from "../api";
import type { NotificationCategory, NotificationItem, NotificationSummary, Pagination } from "../types";
import { crmStore } from "./crm";


const recent = ref<NotificationItem[]>([]);
const items = ref<NotificationItem[]>([]);
const summary = ref<NotificationSummary>({ unread_count: 0, critical_count: 0 });
const pagination = ref<Pagination>({ page: 1, pageSize: 25, total: 0, totalPages: 1 });
const loading = ref(false);
const error = ref("");

function auth() {
  return [crmStore.token.value, crmStore.tenantId.value] as const;
}

async function refreshRecent() {
  if (!crmStore.token.value || !crmStore.tenantId.value) return;
  const [summaryResult, page] = await Promise.all([
    api<NotificationSummary>("/notifications/summary", {}, ...auth()),
    apiPage<NotificationItem>(
      buildQuery("/notifications", { unread_only: true, page: 1, page_size: 10 }),
      {},
      ...auth()
    )
  ]);
  summary.value = summaryResult;
  recent.value = page.items;
}

async function refreshInbox(options: {
  page?: number;
  category?: NotificationCategory | "";
  unreadOnly?: boolean;
} = {}) {
  loading.value = true;
  error.value = "";
  try {
    const page = await apiPage<NotificationItem>(
      buildQuery("/notifications", {
        page: options.page ?? pagination.value.page,
        page_size: pagination.value.pageSize,
        category: options.category,
        unread_only: options.unreadOnly
      }),
      {},
      ...auth()
    );
    items.value = page.items;
    pagination.value = page.pagination;
    await refreshRecent();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Не удалось загрузить уведомления";
  } finally {
    loading.value = false;
  }
}

async function setRead(item: NotificationItem, read = true) {
  const updated = await api<NotificationItem>(
    `/notifications/${item.id}/read`,
    post({ read }, "PATCH"),
    ...auth()
  );
  replace(updated);
  await refreshRecent();
  return updated;
}

async function readAll() {
  await api<void>("/notifications/read-all", post({}), ...auth());
  const readAt = new Date().toISOString();
  items.value = items.value.map((item) => ({ ...item, read_at: item.read_at ?? readAt }));
  recent.value = [];
  summary.value = { unread_count: 0, critical_count: 0 };
}

function replace(updated: NotificationItem) {
  items.value = items.value.map((item) => item.id === updated.id ? updated : item);
  recent.value = recent.value
    .map((item) => item.id === updated.id ? updated : item)
    .filter((item) => !item.read_at);
}

export const notificationStore = {
  recent,
  items,
  summary,
  pagination,
  loading,
  error,
  refreshRecent,
  refreshInbox,
  setRead,
  readAll
};

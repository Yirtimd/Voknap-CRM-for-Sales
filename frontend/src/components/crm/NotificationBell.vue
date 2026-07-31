<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { notificationStore } from "../../stores/notifications";
import type { NotificationItem } from "../../types";
import UiIcon from "../ui/UiIcon.vue";

const router = useRouter();
const open = ref(false);
const root = ref<HTMLElement | null>(null);
let refreshTimer: number | undefined;

onMounted(() => {
  void notificationStore.refreshRecent();
  refreshTimer = window.setInterval(() => void notificationStore.refreshRecent(), 60_000);
  window.addEventListener("pointerdown", closeOutside);
});

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer);
  window.removeEventListener("pointerdown", closeOutside);
});

function closeOutside(event: PointerEvent) {
  if (open.value && event.target instanceof Node && !root.value?.contains(event.target)) {
    open.value = false;
  }
}

async function toggle() {
  open.value = !open.value;
  if (open.value) await notificationStore.refreshRecent();
}

async function openNotification(item: NotificationItem) {
  if (!item.read_at) await notificationStore.setRead(item);
  open.value = false;
  await router.push(item.link || "/inbox?tab=notifications");
}

async function openInbox() {
  open.value = false;
  await router.push("/inbox?tab=notifications");
}
</script>

<template>
  <div ref="root" class="notification-bell">
    <button
      type="button"
      class="secondary notification-bell__trigger"
      aria-label="Уведомления"
      :aria-expanded="open"
      @click="toggle"
    >
      <UiIcon name="bell" :size="20" />
      <b v-if="notificationStore.summary.value.unread_count">
        {{ notificationStore.summary.value.unread_count > 99 ? "99+" : notificationStore.summary.value.unread_count }}
      </b>
    </button>
    <section v-if="open" class="notification-bell__popover" role="dialog" aria-label="Новые уведомления">
      <header>
        <div><strong>Уведомления</strong><small>{{ notificationStore.summary.value.unread_count }} непрочитанных</small></div>
        <button type="button" class="notification-bell__all" @click="openInbox">Все</button>
      </header>
      <button
        v-for="item in notificationStore.recent.value"
        :key="item.id"
        type="button"
        class="notification-bell__row"
        @click="openNotification(item)"
      >
        <i :class="`priority-${item.priority}`"></i>
        <span><strong>{{ item.title }}</strong><small>{{ item.body || item.category }}</small><time>{{ new Date(item.created_at).toLocaleString("ru-RU") }}</time></span>
      </button>
      <p v-if="!notificationStore.recent.value.length" class="notification-bell__empty">Новых уведомлений нет</p>
    </section>
  </div>
</template>

<style scoped>
.notification-bell{position:relative}.notification-bell__trigger{position:relative;width:40px;height:40px;padding:0}.notification-bell__trigger b{position:absolute;top:-5px;right:-6px;display:grid;place-items:center;min-width:19px;height:19px;border:2px solid var(--color-surface);border-radius:999px;padding:0 4px;color:#fff;background:var(--color-danger);font-size:10px}.notification-bell__popover{position:absolute;z-index:90;top:calc(100% + 8px);right:0;width:min(360px,calc(100vw - 28px));overflow:hidden;border:1px solid var(--color-border);border-radius:var(--radius-card);background:var(--color-surface);box-shadow:var(--shadow-popover)}.notification-bell__popover>header{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--color-border-subtle);padding:12px 14px}.notification-bell__popover header div,.notification-bell__row span{display:grid;min-width:0;gap:2px}.notification-bell__popover small,.notification-bell__row time{color:var(--color-text-muted);font-size:var(--font-size-caption)}.notification-bell__all{min-height:30px;border:0;padding:4px 8px;color:var(--color-primary);background:transparent}.notification-bell__row{width:100%;display:grid;grid-template-columns:9px minmax(0,1fr);align-items:start;gap:10px;border:0;border-bottom:1px solid var(--color-border-subtle);border-radius:0;padding:12px 14px;color:var(--color-text-primary);background:transparent;text-align:left}.notification-bell__row:hover{background:var(--color-primary-soft)}.notification-bell__row i{width:8px;height:8px;margin-top:5px;border-radius:50%;background:var(--color-primary)}.notification-bell__row i.priority-high{background:var(--color-warning)}.notification-bell__row i.priority-critical{background:var(--color-danger)}.notification-bell__row strong,.notification-bell__row small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.notification-bell__empty{margin:0;padding:24px;color:var(--color-text-muted);text-align:center}
</style>

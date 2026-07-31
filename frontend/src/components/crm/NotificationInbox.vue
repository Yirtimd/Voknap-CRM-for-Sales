<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

import { notificationStore } from "../../stores/notifications";
import type { NotificationCategory, NotificationItem } from "../../types";
import UiBadge from "../ui/UiBadge.vue";
import UiButton from "../ui/UiButton.vue";
import UiEmptyState from "../ui/UiEmptyState.vue";
import UiIcon from "../ui/UiIcon.vue";

const router = useRouter();
const category = ref<NotificationCategory | "">("");
const unreadOnly = ref(false);
const selectedId = ref("");
const selected = computed(() =>
  notificationStore.items.value.find((item) => item.id === selectedId.value)
  ?? notificationStore.items.value[0]
  ?? null
);

watch([category, unreadOnly], () => void refresh(1));
watch(() => notificationStore.items.value, (items) => {
  if (!items.some((item) => item.id === selectedId.value)) selectedId.value = items[0]?.id ?? "";
}, { immediate: true });

onMounted(() => void refresh(1));

function refresh(page = notificationStore.pagination.value.page) {
  return notificationStore.refreshInbox({ page, category: category.value, unreadOnly: unreadOnly.value });
}

async function select(item: NotificationItem) {
  selectedId.value = item.id;
  if (!item.read_at) await notificationStore.setRead(item);
}

async function follow(item: NotificationItem) {
  if (!item.read_at) await notificationStore.setRead(item);
  if (item.link) await router.push(item.link);
}

function categoryLabel(value: NotificationCategory) {
  return ({ automation: "Автоматизация", approval: "Согласование", task: "Задача", communication: "Коммуникация", system: "Система" })[value];
}
</script>

<template>
  <section class="notification-inbox">
    <header class="notification-toolbar">
      <div class="notification-filters">
        <select v-model="category" aria-label="Категория уведомлений"><option value="">Все категории</option><option value="automation">Автоматизация</option><option value="approval">Согласования</option><option value="task">Задачи</option><option value="communication">Коммуникации</option><option value="system">Системные</option></select>
        <label><input v-model="unreadOnly" type="checkbox" /> Только непрочитанные</label>
      </div>
      <div><UiButton variant="secondary" icon="refresh" :loading="notificationStore.loading.value" @click="refresh()">Обновить</UiButton><UiButton variant="secondary" :disabled="!notificationStore.summary.value.unread_count" @click="notificationStore.readAll">Прочитать все</UiButton></div>
    </header>
    <p v-if="notificationStore.error.value" class="notification-error">{{ notificationStore.error.value }}</p>
    <section class="notification-workspace">
      <aside class="notification-list">
        <button v-for="item in notificationStore.items.value" :key="item.id" type="button" class="notification-row" :class="{ active: selected?.id === item.id, unread: !item.read_at }" @click="select(item)">
          <span class="notification-icon" :class="`priority-${item.priority}`"><UiIcon :name="item.category === 'task' ? 'tasks' : item.category === 'communication' ? 'mail' : item.category === 'approval' ? 'check' : 'automation'" :size="17" /></span>
          <span><strong>{{ item.title }}</strong><small>{{ item.body || categoryLabel(item.category) }}</small><time>{{ new Date(item.created_at).toLocaleString("ru-RU") }}</time></span>
          <i v-if="!item.read_at" aria-label="Непрочитано"></i>
        </button>
        <UiEmptyState v-if="!notificationStore.loading.value && !notificationStore.items.value.length" compact title="Уведомлений нет" description="События CRM и автоматизации появятся здесь." icon="bell" />
      </aside>
      <article v-if="selected" class="notification-detail">
        <header><div><p class="eyebrow">{{ categoryLabel(selected.category) }}</p><h3>{{ selected.title }}</h3><p>{{ new Date(selected.created_at).toLocaleString("ru-RU") }}</p></div><UiBadge :tone="selected.priority === 'critical' ? 'danger' : selected.priority === 'high' ? 'warning' : 'info'">{{ selected.priority }}</UiBadge></header>
        <p>{{ selected.body || "Дополнительное описание отсутствует." }}</p>
        <div class="notification-actions"><UiButton v-if="selected.read_at" variant="secondary" @click="notificationStore.setRead(selected, false)">Отметить непрочитанным</UiButton><UiButton v-if="selected.link" @click="follow(selected)">Открыть объект</UiButton></div>
      </article>
      <UiEmptyState v-else title="Выберите уведомление" description="Здесь появятся детали события." icon="bell" />
    </section>
    <footer v-if="notificationStore.pagination.value.totalPages > 1" class="notification-pages"><UiButton variant="secondary" :disabled="notificationStore.pagination.value.page <= 1" @click="refresh(notificationStore.pagination.value.page - 1)">Назад</UiButton><span>{{ notificationStore.pagination.value.page }} / {{ notificationStore.pagination.value.totalPages }}</span><UiButton variant="secondary" :disabled="notificationStore.pagination.value.page >= notificationStore.pagination.value.totalPages" @click="refresh(notificationStore.pagination.value.page + 1)">Далее</UiButton></footer>
  </section>
</template>

<style scoped>
.notification-inbox{display:grid;gap:12px}.notification-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px}.notification-toolbar>div,.notification-filters{display:flex;align-items:center;gap:8px}.notification-filters label{display:flex;align-items:center;gap:7px;color:var(--color-text-muted);font-size:var(--font-size-meta)}.notification-workspace{display:grid;grid-template-columns:minmax(320px,420px) minmax(0,1fr);min-height:560px;overflow:hidden;border:1px solid var(--color-border);border-radius:var(--radius-panel);background:var(--color-surface)}.notification-list{overflow:auto;border-right:1px solid var(--color-border)}.notification-row{width:100%;display:grid;grid-template-columns:38px minmax(0,1fr) 8px;align-items:start;gap:10px;border:0;border-bottom:1px solid var(--color-border-subtle);border-radius:0;padding:13px;color:var(--color-text-primary);background:transparent;text-align:left}.notification-row:hover,.notification-row.active{background:var(--color-primary-soft)}.notification-row.active{box-shadow:inset 3px 0 var(--color-primary)}.notification-row.unread strong{font-weight:800}.notification-row>span:nth-child(2){display:grid;min-width:0;gap:3px}.notification-row small,.notification-row time{overflow:hidden;color:var(--color-text-muted);font-size:var(--font-size-caption);text-overflow:ellipsis;white-space:nowrap}.notification-row>i{width:7px;height:7px;margin-top:7px;border-radius:50%;background:var(--color-primary)}.notification-icon{display:grid;place-items:center;width:36px;height:36px;border-radius:var(--radius-control);color:var(--color-primary);background:var(--color-primary-soft)}.notification-icon.priority-high{color:var(--color-warning)}.notification-icon.priority-critical{color:var(--color-danger)}.notification-detail{display:grid;align-content:start;gap:24px;padding:24px}.notification-detail>header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;border-bottom:1px solid var(--color-border-subtle);padding-bottom:18px}.notification-detail h3{margin:4px 0 6px;font-size:24px}.notification-detail header p:last-child,.notification-detail>p{color:var(--color-text-muted)}.notification-actions{display:flex;justify-content:flex-end;gap:8px}.notification-pages{display:flex;align-items:center;justify-content:center;gap:12px}.notification-error{color:var(--color-danger)}@media(max-width:820px){.notification-toolbar{align-items:stretch;flex-direction:column}.notification-toolbar>div{flex-wrap:wrap}.notification-workspace{grid-template-columns:1fr;min-height:0}.notification-list{max-height:420px;border-right:0}.notification-detail{border-top:1px solid var(--color-border)}}@media(max-width:560px){.notification-filters{align-items:stretch;flex-direction:column}.notification-toolbar>div>*{flex:1}.notification-detail{padding:18px 14px}}
</style>
